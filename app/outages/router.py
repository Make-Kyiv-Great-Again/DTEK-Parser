import logging
from typing import List
from fastapi import APIRouter, Query, Body

from app.outages.schemas import StatusResponse, AddressItem, BatchStatusResponseItem
from app.outages.service import outage_service
from app.yasno.service import yasno_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

@router.get("/status", response_model=StatusResponse)
async def get_status(
    regionId: int = Query(..., description="Region ID (e.g. 25 for Kyiv)"),
    streetName: str = Query(..., description="Street name (e.g. Вишнева)"),
    houseName: str = Query(..., description="House number (e.g. 12б)"),
    dsoId: int = Query(..., description="DSO ID (e.g. 902 for DTEK Kyiv Grids)")
):
    """Retrieve full outage information, planned schedule, and live status for a street address."""
    # 1. Resolve street
    street_id, resolved_street_name = await yasno_service.resolve_street_id(
        regionId, streetName, dsoId, allow_split_fallback=True
    )
    
    # 2. Resolve house
    house_id, resolved_house_name = await yasno_service.resolve_house_id(
        regionId, street_id, houseName, dsoId
    )
    
    # 3. Retrieve status
    return await outage_service.get_status(
        region_id=regionId,
        street_id=street_id,
        house_id=house_id,
        dso_id=dsoId,
        street_name=resolved_street_name,
        house_name=resolved_house_name
    )

@router.get("/status/coordinates", response_model=StatusResponse)
async def get_status_by_coordinates(
    lat: float = Query(..., description="Latitude of the location"),
    lon: float = Query(..., description="Longitude of the location")
):
    """Resolve geographic coordinates (lat/lon) to a street address and retrieve outage status."""
    return await outage_service.get_status_by_coordinates(lat, lon)

@router.post("/status/batch", response_model=List[BatchStatusResponseItem])
async def get_status_batch(
    items: List[AddressItem] = Body(..., description="List of street name and house number objects")
):
    """Retrieve outage status for a list of addresses in a single batch request."""
    return await outage_service.get_status_batch(items)
