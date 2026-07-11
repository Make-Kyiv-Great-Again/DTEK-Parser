import re
import logging
from typing import Dict, Any, Optional, Tuple
from app.services.dtek_client import dtek_client
from app.utils.normalization import normalize_house

logger = logging.getLogger(__name__)

class DtekService:
    def get_default_city(self, dso_id: int) -> str:
        """Resolve the default city based on the DSO ID."""
        if dso_id == 902:
            return "м. Київ"
        elif dso_id == 301:
            return "Дніпро"
        elif dso_id == 901:
            return ""
        return "м. Київ"

    def normalize_city(self, dso_id: int, city: str) -> str:
        """Normalize city name to match DTEK's internal database structure."""
        city = city.strip()
        if dso_id == 301:  # Dnipro
            if city == "Дніпро":
                return "м. Дніпро"
            if city and not (city.startswith("м. ") or city.startswith("с. ") or city.startswith("смт ")):
                return f"м. {city}"
        elif dso_id == 901:  # Kyiv Oblast
            if city and not (city.startswith("м. ") or city.startswith("с. ") or city.startswith("смт ")):
                return f"м. {city}"
        elif dso_id == 902:  # Kyiv City
            if city == "Київ":
                return "м. Київ"
        return city

    def find_matched_house(self, house_name: str, dtek_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Match target house name with DTEK response data keys."""
        target_norm = normalize_house(house_name)
        for key, val in dtek_data.items():
            if normalize_house(key) == target_norm:
                return val
        return None

    def parse_group_info(self, sub_type_reasons: list) -> Tuple[int, int, str]:
        """Parse group, subgroup, and group key from DTEK status reasons."""
        group = 1
        subgroup = 1
        raw_group_key = "1.1"

        if sub_type_reasons:
            raw_reason = sub_type_reasons[0]
            grp_match = re.search(r'(?:GPV)?(\d+)(?:\.(\d+))?', raw_reason)
            if grp_match:
                group = int(grp_match.group(1))
                subgroup = int(grp_match.group(2)) if grp_match.group(2) else 1
                raw_group_key = f"{group}.{subgroup}"
        
        return group, subgroup, raw_group_key

    def extract_power_status(self, matched_val: Dict[str, Any]) -> Tuple[str, str]:
        """Determine live power status and status reason from matched DTEK house record."""
        start_date = matched_val.get("start_date", "")
        end_date = matched_val.get("end_date", "")
        type_val = matched_val.get("type", "")
        sub_type = matched_val.get("sub_type", "")

        if start_date != "" or end_date != "" or type_val != "":
            power_status = "OFF"
            status_reason = f"Активне відключення: з {start_date} до {end_date}."
            if sub_type:
                status_reason += f" Тип: {sub_type}"
        else:
            power_status = "ON"
            status_reason = "Світло є (відключення не зафіксовано)"

        return power_status, status_reason

    async def get_live_status(
        self, dso_id: int, city: str, street_name: str, house_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Queries DTEK API for live status and parses the outage and group assignment info.
        Returns a dictionary if house matches, or None if house is not found in DTEK.
        """
        if not city:
            city = self.get_default_city(dso_id)

        normalized_city = self.normalize_city(dso_id, city)

        try:
            dtek_res = await dtek_client.fetch_live_status(dso_id, normalized_city, street_name)
        except Exception as e:
            logger.warning(f"Live DTEK query failed: {e}")
            return None

        dtek_data = dtek_res.get("data", {})
        last_update = dtek_res.get("updateTimestamp")

        matched_val = self.find_matched_house(house_name, dtek_data)
        if matched_val is None:
            return None

        power_status, status_reason = self.extract_power_status(matched_val)
        sub_type_reasons = matched_val.get("sub_type_reason", [])
        group, subgroup, raw_group_key = self.parse_group_info(sub_type_reasons)

        return {
            "power_status": power_status,
            "status_reason": status_reason,
            "group": group,
            "subgroup": subgroup,
            "raw_group_key": raw_group_key,
            "last_update": last_update
        }

dtek_service = DtekService()
