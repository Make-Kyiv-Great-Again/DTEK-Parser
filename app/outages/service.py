import logging
from typing import Dict, Any, List
from datetime import datetime
from zoneinfo import ZoneInfo

from app.outages.geocoding import geocoding_service
from app.yasno.service import yasno_service
from app.dtek.service import dtek_service
from app.core.exceptions import AddressNotFoundError

logger = logging.getLogger(__name__)

class OutageService:
    async def get_status(
        self, region_id: int, street_id: int, house_id: int, dso_id: int, street_name: str, house_name: str
    ) -> Dict[str, Any]:
        """Synthesizes status by fetching group assignments, planned/probable schedules, and live DTEK reports."""
        
        # 1. Fetch group assignments
        group, subgroup, raw_group_key = await yasno_service.get_house_group(region_id, street_id, house_id, dso_id)
        
        # Mapped group key (e.g. "1" or "1.1")
        mapped_group_key = raw_group_key
        if dso_id == 902:  # Kyiv Grids uses 1-6 group naming
            mapped_group_key = str(group)

        # 2. Fetch planned outages
        planned_schedule_info = await yasno_service.get_planned_outages(region_id, dso_id, raw_group_key)
        
        # 3. Fetch weekly recurrent schedules
        weekly_schedule = await yasno_service.get_weekly_schedule(region_id, dso_id, mapped_group_key)

        # 4. Fetch live status from DTEK (for DTEK providers)
        dtek_houses = {}
        if dso_id in [901, 902]:  # Kyiv Grids / Kyiv Oblast Grids
            dtek_houses = await dtek_service.get_live_street_data(dso_id, "Київ", street_name)

        matched_live = dtek_service.find_matched_house(house_name, dtek_houses)

        # 5. Determine current status
        if matched_live:
            power_status, status_reason = dtek_service.extract_power_status(matched_live)
        else:
            power_status, status_reason = self.compute_scheduled_status(
                planned_schedule_info, weekly_schedule, mapped_group_key
            )

        has_power = power_status in ["ON", "PROBABLE"]
        last_update = datetime.now(ZoneInfo("Europe/Kyiv")).isoformat()

        # Build human-readable region name
        region_name = "Київ" if region_id == 25 else "Дніпро"

        return {
            "region_id": region_id,
            "street_id": street_id,
            "house_id": house_id,
            "dso_id": dso_id,
            "region_name": region_name,
            "street_name": street_name,
            "house_name": house_name,
            "group_assignment": {
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

        # Standard settings defaults
        region_id = 25
        dso_id = 902
        
        results = []
        
        # Process each street sequentially (or concurrently per street)
        for street_name, houses in by_street.items():
            try:
                # 1. Resolve street once
                street_id, resolved_street_name = await yasno_service.resolve_street_id(
                    region_id, street_name, dso_id, allow_split_fallback=True
                )
                
                # Fetch DTEK live data for the street once
                dtek_houses = {}
                if dso_id in [901, 902]:
                    dtek_houses = await dtek_service.get_live_street_data(dso_id, "Київ", resolved_street_name)

                # Fetch schedules once per street group key lookup (optimized on client internally via caching)
                # But here we resolve houses individually
                for house_name in houses:
                    try:
                        house_id, resolved_house = await yasno_service.resolve_house_id(
                            region_id, street_id, house_name, dso_id
                        )
                        
                        group, subgroup, raw_group_key = await yasno_service.get_house_group(
                            region_id, street_id, house_id, dso_id
                        )
                        
                        mapped_group_key = raw_group_key
                        if dso_id == 902:
                            mapped_group_key = str(group)

                        planned = await yasno_service.get_planned_outages(region_id, dso_id, raw_group_key)
                        weekly = await yasno_service.get_weekly_schedule(region_id, dso_id, mapped_group_key)

                        matched_live = dtek_service.find_matched_house(resolved_house, dtek_houses)
                        if matched_live:
                            status, reason = dtek_service.extract_power_status(matched_live)
                        else:
                            status, reason = self.compute_scheduled_status(planned, weekly, mapped_group_key)

                        results.append({
                            "streetName": street_name,
                            "houseName": house_name,
                            "status": status,
                            "reason": reason
                        })
                    except Exception as e:
                        logger.warning(f"Failed to resolve status in batch for {street_name}, {house_name}: {e}")
                        results.append({
                            "streetName": street_name,
                            "houseName": house_name,
                            "status": "UNKNOWN",
                            "reason": f"Resolution failed: {str(e)}"
                        })
            except Exception as e:
                logger.warning(f"Failed to resolve street in batch for '{street_name}': {e}")
                for house_name in houses:
                    results.append({
                        "streetName": street_name,
                        "houseName": house_name,
                        "status": "UNKNOWN",
                        "reason": f"Street resolution failed: {str(e)}"
                    })
                    
        return results

    def compute_scheduled_status(
        self, planned_info: Dict[str, Any], weekly_schedule: List[Dict[str, Any]], group_key: str
    ) -> tuple[str, str]:
        """Computes current outage status based on planned outages or weekly recurrent schedules."""
        # A. Check planned outages first
        today_plan = planned_info.get("today")
        if today_plan:
            status_type = today_plan.get("status", "")
            if status_type == "EmergencyOutages":
                return "EMERGENCY", "Emergency outages are active in your area."
            elif status_type == "NoOutages":
                return "ON", "No active planned outages for today."
            elif status_type == "ScheduledOutages":
                slots = today_plan.get("slots", [])
                current_hour = datetime.now(ZoneInfo("Europe/Kyiv")).hour
                for slot in slots:
                    if slot.get("start", 0) <= current_hour < slot.get("end", 24):
                        slot_type = slot.get("type", "")
                        if slot_type == "shutdown":
                            return "OFF", f"Scheduled Outage: Active ({slot.get('start')}:00 - {slot.get('end')}:00)"
                        elif slot_type == "possibleShutdown":
                            return "PROBABLE", f"Possible Outage: Active ({slot.get('start')}:00 - {slot.get('end')}:00)"

        # B. Fallback to weekly schedule
        if weekly_schedule:
            now = datetime.now(ZoneInfo("Europe/Kyiv"))
            current_hour = now.hour
            # 0 is Monday, 6 is Sunday
            current_day = now.weekday()
            
            # Map Python weekday (0-6) to Yasno weekday (1-7, where Monday is 1, Sunday is 7)
            yasno_day = current_day + 1
            
            for slot in weekly_schedule:
                if slot.get("day") == yasno_day:
                    hour_status = slot.get("hours", [])
                    if len(hour_status) > current_hour:
                        status_val = hour_status[current_hour]
                        # Yasno weekly hours value meanings:
                        # 0 - Stable Power (ON)
                        # 1 - Definite Outage (OFF)
                        # 2 - Possible Outage (PROBABLE)
                        if status_val == 1:
                            return "OFF", f"Weekly Schedule: Outage Active (Group {group_key})"
                        elif status_val == 2:
                            return "PROBABLE", f"Weekly Schedule: Possible Outage Active (Group {group_key})"
                            
        return "ON", "No active scheduled outage at the current time."

outage_service = OutageService()
