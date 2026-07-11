import logging
from typing import List, Tuple, Dict, Any, Optional
from app.services.yasno_client import yasno_client
from app.core.exceptions import AddressNotFoundError, OutageGroupNotFoundError
from app.utils.normalization import clean_street_name, normalize_house, extract_numeric_part

logger = logging.getLogger(__name__)

class YasnoService:
    async def get_regions(self) -> list:
        """Fetch all available regions and their DSOs. Falls back to static list if API fails."""
        try:
            return await yasno_client.fetch_regions()
        except Exception as e:
            logger.warning(f"Failed to fetch regions from Yasno: {e}. Using static fallback.")
            return [
                {
                    "id": 25,
                    "value": "Київ",
                    "hasCities": False,
                    "dsos": [{"id": 902, "name": "ПРАТ «ДТЕК КИЇВСЬКІ ЕЛЕКТРОМЕРЕЖІ»"}]
                },
                {
                    "id": 3,
                    "value": "Дніпро",
                    "hasCities": True,
                    "dsos": [
                        {"id": 301, "name": "ДнЕМ"},
                        {"id": 303, "name": "ЦЕК"}
                    ]
                }
            ]

    async def resolve_street_id(
        self, region_id: int, street_name: str, dso_id: int, allow_split_fallback: bool = False
    ) -> Tuple[int, str]:
        """
        Cleans street name and searches for it in Yasno.
        Supports apostrophe fallback variations and split-word lookup fallback.
        Returns a tuple of (street_id, street_name).
        Raises AddressNotFoundError if no street matches.
        """
        cleaned_query = clean_street_name(street_name)
        if not cleaned_query:
            raise AddressNotFoundError("Empty street name query.")

        # Stage 1: Try with cleaned street name
        streets = await yasno_client.search_streets(region_id, cleaned_query, dso_id)

        # Stage 1b: Apostrophe variant lookups
        apostrophes = ["'", "’", "ʼ", "`"]
        if not streets and any(ap in cleaned_query for ap in apostrophes):
            current_ap = next(ap for ap in apostrophes if ap in cleaned_query)
            for ap in apostrophes:
                if ap == current_ap:
                    continue
                variant_query = cleaned_query.replace(current_ap, ap)
                try:
                    streets = await yasno_client.search_streets(region_id, variant_query, dso_id)
                    if streets:
                        break
                except Exception:
                    pass

        # Stage 2: Fallback to original geocoded/input name
        if not streets:
            try:
                streets = await yasno_client.search_streets(region_id, street_name, dso_id)
                # Try apostrophe variants on original name as well
                if not streets and any(ap in street_name for ap in apostrophes):
                    current_ap = next(ap for ap in apostrophes if ap in street_name)
                    for ap in apostrophes:
                        if ap == current_ap:
                            continue
                        variant_query = street_name.replace(current_ap, ap)
                        streets = await yasno_client.search_streets(region_id, variant_query, dso_id)
                        if streets:
                            break
            except Exception:
                pass

        # Stage 3: Split cleaned query and try last word (main identifier, e.g. "Палладіна")
        if not streets and allow_split_fallback and " " in cleaned_query:
            words = [w for w in cleaned_query.split() if len(w) > 2]
            if words:
                try:
                    streets = await yasno_client.search_streets(region_id, words[-1], dso_id)
                except Exception:
                    pass

        if not streets:
            raise AddressNotFoundError(f"Street '{street_name}' not found in operator's database.")

        matched = streets[0]
        return matched["id"], matched["value"]

    async def resolve_house_id(
        self, region_id: int, street_id: int, house_name: str, dso_id: int
    ) -> Tuple[int, str]:
        """
        Resolves a house ID and normalized name on a street.
        Matches using:
          A. Exact normalized match.
          B. Partial match.
          C. Fallback to closest numeric house number.
        Returns a tuple of (house_id, house_name).
        Raises AddressNotFoundError if no houses exist or match.
        """
        houses = await yasno_client.search_houses(region_id, street_id, "", dso_id)
        if not houses:
            raise AddressNotFoundError("No houses found on this street in operator's database.")

        target_norm = normalize_house(house_name)
        matched_house = None

        # A. Try exact match first
        for h in houses:
            if normalize_house(h["value"]) == target_norm:
                matched_house = h
                break

        # B. Try partial match
        if not matched_house:
            for h in houses:
                h_norm = normalize_house(h["value"])
                if target_norm != "" and (target_norm in h_norm or h_norm in target_norm):
                    matched_house = h
                    break

        # C. Fallback: Find closest numeric match
        if not matched_house:
            target_num = extract_numeric_part(house_name)
            min_diff = float('inf')
            for h in houses:
                h_num = extract_numeric_part(h["value"])
                diff = abs(h_num - target_num)
                if diff < min_diff:
                    min_diff = diff
                    matched_house = h

        if not matched_house:
            raise AddressNotFoundError(f"House '{house_name}' could not be matched on street ID {street_id}.")

        return matched_house["id"], matched_house["value"]

    async def get_house_group(self, region_id: int, street_id: int, house_id: int, dso_id: int) -> Tuple[int, int, str]:
        """
        Fetches the raw group assignment for a house from Yasno.
        Returns tuple: (group, subgroup, raw_group_key).
        Raises OutageGroupNotFoundError if not found.
        """
        try:
            group_data = await yasno_client.fetch_house_group(region_id, street_id, house_id, dso_id)
        except Exception as e:
            raise OutageGroupNotFoundError(f"Failed to fetch outage group from Yasno: {e}")

        if not group_data or "group" not in group_data:
            raise OutageGroupNotFoundError("Outage group not found for this house address.")

        group = group_data["group"]
        subgroup = group_data.get("subgroup", 1)
        raw_group_key = f"{group}.{subgroup}"
        return group, subgroup, raw_group_key

    async def get_planned_outages(self, region_id: int, dso_id: int, raw_group_key: str) -> Dict[str, Any]:
        """Fetches planned outages data for a given group key."""
        try:
            planned_resp = await yasno_client.fetch_planned_outages(region_id, dso_id)
            return planned_resp.get(raw_group_key, {})
        except Exception as e:
            logger.warning(f"Failed to fetch planned outages: {e}")
            return {}

    async def get_weekly_schedule(self, region_id: int, dso_id: int, mapped_group_key: str) -> Optional[List[Dict[str, Any]]]:
        """Fetches the weekly schedule (slots) for a mapped group key."""
        try:
            probable_resp = await self.get_raw_probable_outages(region_id, dso_id)
            reg_key = str(region_id)
            dso_key = str(dso_id)
            if reg_key in probable_resp and "dsos" in probable_resp[reg_key]:
                dsos = probable_resp[reg_key]["dsos"]
                if dso_key in dsos and "groups" in dsos[dso_key]:
                    groups_dict = dsos[dso_key]["groups"]
                    if mapped_group_key in groups_dict:
                        return groups_dict[mapped_group_key].get("slots")
        except Exception as e:
            logger.warning(f"Failed to fetch probable outages: {e}")
        return None

    async def get_raw_planned_outages(self, region_id: int, dso_id: int) -> Dict[str, Any]:
        """Fetches raw planned outages dict from Yasno API."""
        return await yasno_client.fetch_planned_outages(region_id, dso_id)

    async def get_raw_probable_outages(self, region_id: int, dso_id: int) -> Dict[str, Any]:
        """Fetches raw probable (weekly) outages dict from Yasno API."""
        return await yasno_client.fetch_probable_outages(region_id, dso_id)

    async def search_streets(self, region_id: int, query: str, dso_id: int) -> list:
        """Pass-through search query for streets via client."""
        return await yasno_client.search_streets(region_id, query, dso_id)

    async def search_houses(self, region_id: int, street_id: int, query: str, dso_id: int) -> list:
        """Pass-through search query for houses via client."""
        return await yasno_client.search_houses(region_id, street_id, query, dso_id)

yasno_service = YasnoService()
