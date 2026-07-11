import logging
from typing import List
from fastapi import APIRouter, Query

from app.yasno.schemas import RegionInfo, StreetInfo, HouseInfo
from app.yasno.service import yasno_service

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
