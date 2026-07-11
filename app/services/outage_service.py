import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from app.core.exceptions import InvalidInputError
from app.services.yasno_client import yasno_client
from app.services.dtek_client import dtek_client
from app.services.yasno_service import yasno_service
from app.services.dtek_service import dtek_service
from app.services.geocoding_service import geocoding_service

logger = logging.getLogger(__name__)

class OutageService:
    def compute_scheduled_status(
        self,
        planned_data: Dict[str, Any],
        weekly_schedule: Optional[List[Dict[str, Any]]],
        mapped_group_key: str
    ) -> Tuple[str, str]:
        """Determine power status based on planned/weekly schedules."""
        from zoneinfo import ZoneInfo
        import datetime

        kyiv_tz = ZoneInfo("Europe/Kyiv")
        now = datetime.datetime.now(kyiv_tz)
        current_weekday = now.weekday()
        current_minute = now.hour * 60 + now.minute

        today_planned = planned_data.get("today", {})
        today_status = today_planned.get("status", "")
        today_slots = today_planned.get("slots", [])

        if today_status == "EmergencyOutages":
            return "EMERGENCY", "Emergency blackouts are currently active for your area"

        # A. Check planned slots
        if today_slots:
            for slot in today_slots:
                start = slot.get("start", 0)
                end = slot.get("end", 0)
                if start <= current_minute < end:
                    slot_type = slot.get("type", "")
                    if slot_type == "Definite":
                        return "OFF", "Planned stabilization outage is currently active"
                    if slot_type == "Possible":
                        return "POSSIBLE", "Possible outage active (stabilization backup slot)"

        # B. Check weekly slots
        if weekly_schedule:
            day_key = str(current_weekday)
            day_slots = weekly_schedule.get(day_key, [])
            for slot in day_slots:
                start = slot.get("start", 0)
                end = slot.get("end", 0)
                if start <= current_minute < end:
                    slot_type = slot.get("type", "")
                    if slot_type == "Definite":
                        return "OFF", f"Weekly schedule outage is active (Group {mapped_group_key})"
                    if slot_type == "Possible":
                        return "POSSIBLE", f"Possible outage active per weekly schedule (Group {mapped_group_key})"
                    return "ON", "Power is ON per weekly schedule"

        return "ON", "No active outages detected"

    async def get_status(
        self,
        region_id: Optional[int] = None,
        street_id: Optional[int] = None,
        house_id: Optional[int] = None,
        dso_id: Optional[int] = None,
        street_name: Optional[str] = None,
        house_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates outage details, planned schedule, and weekly schedule.
        Either (region_id, street_id, house_id, dso_id) must be provided,
        or (street_name, house_name) to search and resolve them.
        """
        # Resolve IDs if missing but names are provided
        if (region_id is None or street_id is None or house_id is None or dso_id is None) and (street_name and house_name):
            if region_id is None:
                region_id = 25
            if dso_id is None:
                dso_id = 902

            street_id, street_name = await yasno_service.resolve_street_id(region_id, street_name, dso_id)
            house_id, house_name = await yasno_service.resolve_house_id(region_id, street_id, house_name, dso_id)

        # Check if we have all required parameters
        if region_id is None or street_id is None or house_id is None or dso_id is None:
            raise InvalidInputError(
                "Missing required parameters. Either provide IDs (regionId, streetId, houseId, dsoId) "
                "or address strings (streetName, houseName)."
            )

        power_status = "ON"
        status_reason = "Світло є (відключення не зафіксовано)"
        last_update = None
        live_queried = False
        group = 1
        subgroup = 1
        raw_group_key = "1.1"

        # Attempt live DTEK query if names are available
        if street_name and house_name:
            if ", " in street_name:
                city, street_part = street_name.split(", ", 1)
            else:
                city = dtek_service.get_default_city(dso_id)
                street_part = street_name

            live_data = await dtek_service.get_live_status(dso_id, city, street_part, house_name)
            if live_data:
                power_status = live_data["power_status"]
                status_reason = live_data["status_reason"]
                group = live_data["group"]
                subgroup = live_data["subgroup"]
                raw_group_key = live_data["raw_group_key"]
                last_update = live_data["last_update"]
                live_queried = True

        # Fallback to Yasno static group assignment if live status lookup didn't succeed
        if not live_queried:
            group, subgroup, raw_group_key = await yasno_service.get_house_group(region_id, street_id, house_id, dso_id)

        # Map group (1-6 range subgroup mapping)
        mapped_group = ((group - 1) % 6) + 1
        mapped_group_key = f"{mapped_group}.{subgroup}"

        # Fetch planned outages
        planned_data = await yasno_service.get_planned_outages(region_id, dso_id, raw_group_key)

        # Fetch weekly probable schedule
        weekly_schedule = await yasno_service.get_weekly_schedule(region_id, dso_id, mapped_group_key)

        # Calculate scheduled status if live query was skipped or found no active outages
        if not live_queried:
            power_status, status_reason = self.compute_scheduled_status(
                planned_data, weekly_schedule, mapped_group_key
            )

        address_str = f"Група {raw_group_key} (Графік {mapped_group_key})"
        has_power = (power_status == "ON" or power_status == "POSSIBLE")

        # Planned Outage Info structure
        planned_schedule_info = None
        if planned_data:
            planned_schedule_info = {
                "today": planned_data.get("today"),
                "tomorrow": planned_data.get("tomorrow"),
                "updatedOn": planned_data.get("updatedOn")
            }

        return {
            "region_id": region_id,
            "street_id": street_id,
            "house_id": house_id,
            "dso_id": dso_id,
            "address": address_str,
            "group_info": {
                "group": group,
                "subgroup": subgroup,
                "raw_group_key": raw_group_key,
                "mapped_group_key": mapped_group_key
            },
            "power_status": power_status,
            "status_reason": status_reason,
            "planned_schedule": planned_schedule_info,
            "weekly_schedule": weekly_schedule,
            "has_power": has_power,
            "group": raw_group_key,
            "last_update": last_update
        }

    async def get_status_by_coordinates(self, lat: float, lon: float) -> Dict[str, Any]:
        """Resolves coordinates to street address and returns status."""
        geo_info = await geocoding_service.reverse_geocode(lat, lon)
        street_name = geo_info["street_name"]
        house_number = geo_info["house_number"]
        region_id = geo_info["region_id"]
        dso_id = geo_info["dso_id"]

        street_id, resolved_street_name = await yasno_service.resolve_street_id(
            region_id, street_name, dso_id, allow_split_fallback=True
        )

        house_id, resolved_house_name = await yasno_service.resolve_house_id(
            region_id, street_id, house_number, dso_id
        )

        return await self.get_status(
            region_id=region_id,
            street_id=street_id,
            house_id=house_id,
            dso_id=dso_id,
            street_name=resolved_street_name,
            house_name=resolved_house_name
        )

    async def get_status_batch(self, items: List[Any]) -> List[Dict[str, Any]]:
        """Resolves outages in batch, grouping by street to optimize requests."""
        from collections import defaultdict
        
        by_street = defaultdict(list)
        for item in items:
            by_street[item.streetName].append(item.houseName)

        planned_cache = {}
        probable_cache = {}

        async def get_cached_schedules(region_id: int, dso_id: int):
            cache_key = f"{region_id}:{dso_id}"
            if cache_key not in planned_cache:
                try:
                    planned_cache[cache_key] = await yasno_service.get_raw_planned_outages(region_id, dso_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch planned outages in batch: {e}")
                    planned_cache[cache_key] = {}
            if cache_key not in probable_cache:
                try:
                    probable_cache[cache_key] = await yasno_service.get_raw_probable_outages(region_id, dso_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch probable outages in batch: {e}")
                    probable_cache[cache_key] = {}
            return planned_cache[cache_key], probable_cache[cache_key]

        results = []
        sem = asyncio.Semaphore(3)

        async def resolve_batch_house(
            street_name: str,
            house_name: str,
            houses: List[Dict[str, Any]],
            dtek_data: Dict[str, Any],
            region_id: int,
            street_id: int,
            dso_id: int
        ) -> Dict[str, Any]:
            try:
                house_id, resolved_house_name = await yasno_service.resolve_house_id(
                    region_id, street_id, house_name, dso_id
                )
            except Exception as e:
                logger.warning(f"Failed to resolve house {house_name} in batch: {e}")
                return {"streetName": street_name, "houseName": house_name, "status": "UNKNOWN"}

            power_status = None
            dtek_matched = dtek_service.find_matched_house(resolved_house_name, dtek_data)
            if dtek_matched is not None:
                power_status, _ = dtek_service.extract_power_status(dtek_matched)
            else:
                try:
                    group, subgroup, raw_group_key = await yasno_service.get_house_group(
                        region_id, street_id, house_id, dso_id
                    )
                    
                    planned_outages, probable_outages = await get_cached_schedules(region_id, dso_id)
                    
                    mapped_group = ((group - 1) % 6) + 1
                    mapped_group_key = f"{mapped_group}.{subgroup}"
                    
                    weekly_schedule = None
                    reg_key = str(region_id)
                    dso_key = str(dso_id)
                    if reg_key in probable_outages and "dsos" in probable_outages[reg_key]:
                        dsos = probable_outages[reg_key]["dsos"]
                        if dso_key in dsos and "groups" in dsos[dso_key]:
                            groups_dict = dsos[dso_key]["groups"]
                            if mapped_group_key in groups_dict:
                                weekly_schedule = groups_dict[mapped_group_key].get("slots")

                    planned_data = planned_outages.get(raw_group_key, {})
                    
                    power_status, _ = self.compute_scheduled_status(planned_data, weekly_schedule, mapped_group_key)
                except Exception as ex:
                    logger.warning(f"Yasno fallback failed in batch for house {house_name}: {ex}")
                    power_status = "UNKNOWN"

            if not power_status:
                power_status = "UNKNOWN"

            return {
                "streetName": street_name,
                "houseName": house_name,
                "status": power_status
            }

        async def resolve_street_houses(street_name: str, house_names: List[str]):
            async with sem:
                try:
                    region_id = 25
                    dso_id = 902

                    street_id, resolved_street_name = await yasno_service.resolve_street_id(
                        region_id, street_name, dso_id
                    )
                except Exception as e:
                    logger.warning(f"Error resolving street {street_name} in batch: {e}")
                    for hn in house_names:
                        results.append({"streetName": street_name, "houseName": hn, "status": "UNKNOWN"})
                    return

                try:
                    houses = await yasno_client.search_houses(region_id, street_id, "", dso_id)
                except Exception as e:
                    logger.warning(f"Error listing houses for street {street_name} in batch: {e}")
                    for hn in house_names:
                        results.append({"streetName": street_name, "houseName": hn, "status": "UNKNOWN"})
                    return

                city = dtek_service.get_default_city(dso_id)
                try:
                    dtek_res = await dtek_client.fetch_live_status(dso_id, city, resolved_street_name)
                    dtek_data = dtek_res.get("data", {})
                except Exception as e:
                    logger.warning(f"Live DTEK fetch failed in batch: {e}")
                    dtek_data = {}

                for house_name in house_names:
                    res = await resolve_batch_house(
                        street_name, house_name, houses, dtek_data, region_id, street_id, dso_id
                    )
                    results.append(res)

        tasks = [resolve_street_houses(st, hns) for st, hns in by_street.items()]
        await asyncio.gather(*tasks)
        return results

outage_service = OutageService()
