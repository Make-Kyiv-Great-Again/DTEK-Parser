import logging
from typing import List, Optional

from fastapi import APIRouter, Query

from app.schemas.api import (
    RegionInfo,
    StreetInfo,
    HouseInfo,
    StatusResponse,
    AddressItem,
    BatchStatusResponseItem
)
from app.services.yasno_service import yasno_service
from app.services.outage_service import outage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.get("/regions", response_model=List[RegionInfo])
async def get_regions():
    """Get available regions and distribution system operators (DSOs)."""
    return await yasno_service.get_regions()


@router.get("/streets", response_model=List[StreetInfo])
async def get_streets(
    regionId: int = Query(..., description="Region ID (e.g. 25 for Kyiv)"),
    query: str = Query(..., description="Street name search query"),
    dsoId: int = Query(..., description="DSO ID (e.g. 902 for Kyiv DTEK)")
):
    """Search for street IDs by street name."""
    return await yasno_service.search_streets(regionId, query, dsoId)


@router.get("/houses", response_model=List[HouseInfo])
async def get_houses(
    regionId: int = Query(...),
    streetId: int = Query(...),
    query: str = Query("", description="House number search query"),
    dsoId: int = Query(...)
):
    """Search for house IDs on a specific street."""
    return await yasno_service.search_houses(regionId, streetId, query, dsoId)


@router.get("/status", response_model=StatusResponse)
async def get_status(
    regionId: Optional[int] = Query(None),
    streetId: Optional[int] = Query(None),
    houseId: Optional[int] = Query(None),
    dsoId: Optional[int] = Query(None),
    streetName: Optional[str] = Query(None),
    houseName: Optional[str] = Query(None)
):
    """Retrieve group details, planned schedule, and current outage status for a house."""
    return await outage_service.get_status(
        region_id=regionId,
        street_id=streetId,
        house_id=houseId,
        dso_id=dsoId,
        street_name=streetName,
        house_name=houseName
    )


@router.get("/status/coordinates", response_model=StatusResponse)
async def get_status_by_coordinates(
    lat: float = Query(...),
    lon: float = Query(...)
):
    """Resolve outage status for a house corresponding to geographic coordinates."""
    return await outage_service.get_status_by_coordinates(lat, lon)


@router.post("/status/batch", response_model=List[BatchStatusResponseItem])
async def get_status_batch(items: List[AddressItem]):
    """Query statuses in a batch address list."""
    return await outage_service.get_status_batch(items)
