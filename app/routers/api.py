import datetime
import logging
from typing import List, Optional, Dict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from app.services.yasno_client import yasno_client
from app.services.dtek_client import dtek_client
import re

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

# --- Pydantic Schemas ---

class DsoInfo(BaseModel):
    id: int
    name: str

class RegionInfo(BaseModel):
    id: int
    value: str
    hasCities: bool
    dsos: List[DsoInfo]

class StreetInfo(BaseModel):
    id: int
    value: str

class HouseInfo(BaseModel):
    id: int
    value: str

class GroupAssignment(BaseModel):
    group: int
    subgroup: int
    raw_group_key: str
    mapped_group_key: str

class OutageSlotSchema(BaseModel):
    start: int
    end: int
    type: str

class PlannedDayOutages(BaseModel):
    date: str
    status: str
    slots: List[OutageSlotSchema]

class PlannedOutageInfo(BaseModel):
    today: Optional[PlannedDayOutages] = None
    tomorrow: Optional[PlannedDayOutages] = None
    updatedOn: Optional[str] = None

class StatusResponse(BaseModel):
    region_id: int
    street_id: int
    house_id: int
    dso_id: int
    address: str
    group_info: GroupAssignment
    power_status: str = Field(description="ON, OFF, or EMERGENCY")
    status_reason: str
    planned_schedule: Optional[PlannedOutageInfo] = None
    weekly_schedule: Optional[Dict[str, List[OutageSlotSchema]]] = None
    has_power: bool
    group: str
    last_update: Optional[str] = None

# --- API Routes ---

@router.get("/regions", response_model=List[RegionInfo])
async def get_regions():
    """Get available regions and distribution system operators (DSOs)."""
    try:
        return await yasno_client.fetch_regions()
    except Exception as e:
        logger.error(f"Failed to fetch regions: {e}")
        # Return fallback static regions if API is down
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

@router.get("/streets", response_model=List[StreetInfo])
async def get_streets(
    regionId: int = Query(..., description="Region ID (e.g. 25 for Kyiv)"),
    query: str = Query(..., description="Street name search query"),
    dsoId: int = Query(..., description="DSO ID (e.g. 902 for Kyiv DTEK)")
):
    """Search for street IDs by street name."""
    return await yasno_client.search_streets(regionId, query, dsoId)

@router.get("/houses", response_model=List[HouseInfo])
async def get_houses(
    regionId: int = Query(...),
    streetId: int = Query(...),
    query: str = Query("", description="House number search query"),
    dsoId: int = Query(...)
):
    """Search for house IDs on a specific street."""
    return await yasno_client.search_houses(regionId, streetId, query, dsoId)

@router.get("/status", response_model=StatusResponse)
async def get_status(
    regionId: int = Query(...),
    streetId: int = Query(...),
    houseId: int = Query(...),
    dsoId: int = Query(...),
    streetName: Optional[str] = Query(None),
    houseName: Optional[str] = Query(None)
):
    """Retrieve group details, planned schedule, and current outage status for a house."""
    # 1. Determine group information & live status
    group = 1
    subgroup = 1
    raw_group_key = "1.1"
    power_status = "ON"
    status_reason = "Світло є (відключення не зафіксовано)"
    last_update = None
    live_queried = False

    # Attempt live query if streetName and houseName are provided
    if streetName and houseName:
        try:
            # Parse city and street from the query string
            if ", " in streetName:
                parts = streetName.split(", ", 1)
                city = parts[0]
                street = parts[1]
            else:
                if dsoId == 902:
                    city = "м. Київ"
                elif dsoId == 301:
                    city = "Дніпро"
                elif dsoId == 901:
                    city = ""
                else:
                    city = "м. Київ"
                street = streetName

            # Fetch live status from DTEK client
            dtek_res = await dtek_client.fetch_live_status(dsoId, city, street)
            dtek_data = dtek_res.get("data", {})
            last_update = dtek_res.get("updateTimestamp")

            # Normalization helper for exact key matching
            def normalize_house(h: str) -> str:
                return re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', h).lower()

            target_norm = normalize_house(houseName)
            matched_val = None
            for k, v in dtek_data.items():
                if normalize_house(k) == target_norm:
                    matched_val = v
                    break

            if matched_val is not None:
                start_date = matched_val.get("start_date", "")
                end_date = matched_val.get("end_date", "")
                type_val = matched_val.get("type", "")
                sub_type = matched_val.get("sub_type", "")
                sub_type_reasons = matched_val.get("sub_type_reason", [])

                # Parsing logic for live power status
                if start_date != "" or end_date != "" or type_val != "":
                    power_status = "OFF"
                    status_reason = f"Активне відключення: з {start_date} до {end_date}."
                    if sub_type:
                        status_reason += f" Тип: {sub_type}"
                else:
                    power_status = "ON"
                    status_reason = "Світло є (відключення не зафіксовано)"

                # Parse group details
                if sub_type_reasons:
                    raw_reason = sub_type_reasons[0]
                    grp_match = re.search(r'(?:GPV)?(\d+)(?:\.(\d+))?', raw_reason)
                    if grp_match:
                        group = int(grp_match.group(1))
                        subgroup = int(grp_match.group(2)) if grp_match.group(2) else 1
                        raw_group_key = f"{group}.{subgroup}"
                
                live_queried = True
            else:
                logger.warning(f"House '{houseName}' not found in DTEK live data for street '{streetName}'. Falling back to Yasno.")
        except Exception as e:
            logger.error(f"Live DTEK query failed, falling back to Yasno: {e}")

    # Fallback to Yasno static schedules if live query was skipped or failed
    if not live_queried:
        group_data = await yasno_client.fetch_house_group(regionId, streetId, houseId, dsoId)
        if not group_data or "group" not in group_data:
            raise HTTPException(status_code=404, detail="Outage group not found for this house address.")
        group = group_data["group"]
        subgroup = group_data.get("subgroup", 1)
        raw_group_key = f"{group}.{subgroup}"

    # Map granular group to schedule group key
    mapped_group = ((group - 1) % 6) + 1
    mapped_group_key = f"{mapped_group}.{subgroup}"

    # 2. Fetch planned outages
    planned_data = {}
    try:
        planned_resp = await yasno_client.fetch_planned_outages(regionId, dsoId)
        planned_data = planned_resp.get(raw_group_key, {})
    except Exception as e:
        logger.error(f"Failed to fetch planned outages: {e}")

    # 3. Fetch probable outages (weekly schedule)
    weekly_schedule = None
    try:
        probable_resp = await yasno_client.fetch_probable_outages(regionId, dsoId)
        reg_key = str(regionId)
        dso_key = str(dsoId)
        if reg_key in probable_resp and "dsos" in probable_resp[reg_key]:
            dsos = probable_resp[reg_key]["dsos"]
            if dso_key in dsos and "groups" in dsos[dso_key]:
                groups_dict = dsos[dso_key]["groups"]
                if mapped_group_key in groups_dict:
                    weekly_schedule = groups_dict[mapped_group_key].get("slots")
    except Exception as e:
        logger.error(f"Failed to fetch probable outages: {e}")

    # 4. Fallback status computation if not live queried
    if not live_queried:
        kyiv_tz = ZoneInfo("Europe/Kyiv")
        now = datetime.datetime.now(kyiv_tz)
        current_weekday = now.weekday()
        current_minute = now.hour * 60 + now.minute

        power_status = "ON"
        status_reason = "No active outages detected"

        today_planned = planned_data.get("today", {})
        today_status = today_planned.get("status", "")
        today_slots = today_planned.get("slots", [])

        if today_status == "EmergencyOutages":
            power_status = "EMERGENCY"
            status_reason = "Emergency blackouts are currently active for your area"
        elif today_slots:
            active_planned_slot = None
            for slot in today_slots:
                start = slot.get("start", 0)
                end = slot.get("end", 0)
                if start <= current_minute < end:
                    active_planned_slot = slot
                    break
            
            if active_planned_slot:
                slot_type = active_planned_slot.get("type", "")
                if slot_type == "Definite":
                    power_status = "OFF"
                    status_reason = "Planned stabilization outage is currently active"
                elif slot_type == "Possible":
                    power_status = "POSSIBLE"
                    status_reason = "Possible outage active (stabilization backup slot)"
        else:
            if weekly_schedule:
                day_key = str(current_weekday)
                day_slots = weekly_schedule.get(day_key, [])
                active_weekly_slot = None
                for slot in day_slots:
                    start = slot.get("start", 0)
                    end = slot.get("end", 0)
                    if start <= current_minute < end:
                        active_weekly_slot = slot
                        break
                
                if active_weekly_slot:
                    slot_type = active_weekly_slot.get("type", "")
                    if slot_type == "Definite":
                        power_status = "OFF"
                        status_reason = f"Weekly schedule outage is active (Group {mapped_group_key})"
                    elif slot_type == "Possible":
                        power_status = "POSSIBLE"
                        status_reason = f"Possible outage active per weekly schedule (Group {mapped_group_key})"
                    else:
                        power_status = "ON"
                        status_reason = "Power is ON per weekly schedule"

    # Address context string
    address_str = f"Група {raw_group_key} (Графік {mapped_group_key})"
    has_power = (power_status == "ON" or power_status == "POSSIBLE")

    return StatusResponse(
        region_id=regionId,
        street_id=streetId,
        house_id=houseId,
        dso_id=dsoId,
        address=address_str,
        group_info=GroupAssignment(
            group=group,
            subgroup=subgroup,
            raw_group_key=raw_group_key,
            mapped_group_key=mapped_group_key
        ),
        power_status=power_status,
        status_reason=status_reason,
        planned_schedule=PlannedOutageInfo(
            today=planned_data.get("today"),
            tomorrow=planned_data.get("tomorrow"),
            updatedOn=planned_data.get("updatedOn")
        ) if planned_data else None,
        weekly_schedule=weekly_schedule,
        has_power=has_power,
        group=raw_group_key,
        last_update=last_update
    )

@router.get("/status/coordinates", response_model=StatusResponse)
async def get_status_by_coordinates(
    lat: float = Query(...),
    lon: float = Query(...)
):
    """Resolve outage status for a house corresponding to geographic coordinates."""
    import httpx
    # List of public reverse geocoding instances to try
    geocoder_urls = [
        f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1",
        f"https://nominatim.openstreetmap.fr/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
    ]
    
    geo_data = None
    last_err = None
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            "User-Agent": "SvitloLocatorApp/1.1 (contact: admin@svitlo-finder.xyz; educational wrapper API)"
        }
        for url in geocoder_urls:
            try:
                r = await client.get(url, headers=headers)
                r.raise_for_status()
                geo_data = r.json()
                if geo_data and "address" in geo_data:
                    logger.info(f"Successfully resolved address using geocoder: {url}")
                    break
            except Exception as e:
                logger.warning(f"Geocoder {url} failed: {e}")
                last_err = e

    if not geo_data:
        err_msg = f"Failed to resolve address from coordinates via Nominatim. Error details: {str(last_err)}"
        if last_err and hasattr(last_err, 'response') and last_err.response:
            err_msg += f" (Status code: {last_err.response.status_code}, Body: {last_err.response.text[:200]})"
        logger.error(err_msg)
        raise HTTPException(status_code=502, detail=err_msg)

    address = geo_data.get("address", {})
    
    # 1. Resolve House Number (default to "1" if Nominatim does not provide one)
    house_number = address.get("house_number")
    if not house_number:
        house_number = "1"

    # 2. Resolve Street Name
    street_name = address.get("road") or address.get("street")
    if not street_name:
        raise HTTPException(
            status_code=404,
            detail="Не вдалося визначити назву вулиці за цими координатами."
        )

    # Strip common Ukrainian road prefix/suffix helpers
    def clean_street(name: str) -> str:
        name = re.sub(r'^(вулиця|вул\.|проспект|пр\.|провулок|пров\.|площа|майдан)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(вулиця|вул\.|проспект|пр\.|провулок|пров\.|площа|майдан)$', '', name, flags=re.IGNORECASE)
        return name.strip()

    cleaned_street_query = clean_street(street_name)

    # 3. Resolve Region, DSO, default city based on address state & city details
    state = address.get("state", "")
    city = address.get("city", "") or address.get("town", "") or address.get("village", "")
    
    region_id = 25  # Kyiv
    dso_id = 902   # DTEK Kyiv Grids

    if "Дніпро" in city or "Дніпропетровська" in state:
        region_id = 3
        dso_id = 301
    elif "Київська" in state:
        region_id = 25
        dso_id = 901

    # 4. Search Street in Yasno to get ID
    streets = await yasno_client.search_streets(region_id, cleaned_street_query, dso_id)
    if not streets:
        # Retry without cleaning, just in case
        streets = await yasno_client.search_streets(region_id, street_name, dso_id)
        if not streets:
            raise HTTPException(
                status_code=404,
                detail=f"Вулицю '{street_name}' не знайдено в базі оператора."
            )

    matched_street = streets[0]
    street_id = matched_street["id"]
    resolved_street_name = matched_street["value"]

    # 5. Fetch houses on that street
    houses = await yasno_client.search_houses(region_id, street_id, "", dso_id)
    if not houses:
        raise HTTPException(status_code=404, detail="Не знайдено будинків на цій вулиці в базі оператора.")

    # 6. Match house number, or find the closest available house
    def normalize_house(h: str) -> str:
        return re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', h).lower()

    def extract_numeric_part(house_str: str) -> int:
        match = re.search(r'\d+', house_str)
        return int(match.group()) if match else 1

    target_norm = normalize_house(house_number)
    matched_house = None

    # A. Try exact match first
    for h in houses:
        if normalize_house(h["value"]) == target_norm:
            matched_house = h
            break

    # B. Try partial match
    if not matched_house:
        for h in houses:
            if target_norm != "" and (target_norm in normalize_house(h["value"]) or normalize_house(h["value"]) in target_norm):
                matched_house = h
                break

    # C. Fallback: Find closest numeric match
    if not matched_house:
        target_num = extract_numeric_part(house_number)
        min_diff = float('inf')
        for h in houses:
            h_num = extract_numeric_part(h["value"])
            diff = abs(h_num - target_num)
            if diff < min_diff:
                min_diff = diff
                matched_house = h

    house_id = matched_house["id"]
    resolved_house_name = matched_house["value"]

    # 7. Call status logic
    return await get_status(
        regionId=region_id,
        streetId=street_id,
        houseId=house_id,
        dsoId=dso_id,
        streetName=resolved_street_name,
        houseName=resolved_house_name
    )
