import logging
from typing import Dict, Any
from fastapi import APIRouter, Query
from app.dtek.service import dtek_service
from app.core.exceptions import InvalidInputError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dtek")

@router.get("/viewport", summary="Search DTEK outages by map viewport coordinates")
async def get_dtek_viewport_outages(
    lat_top: float = Query(..., description="Latitude of the top boundary (-90 to 90)"),
    lon_left: float = Query(..., description="Longitude of the left boundary (-180 to 180)"),
    lat_bottom: float = Query(..., description="Latitude of the bottom boundary (-90 to 90)"),
    lon_right: float = Query(..., description="Longitude of the right boundary (-180 to 180)"),
    dsoId: int = Query(902, description="DTEK DSO provider ID (default: 902)"),
    city: str = Query("Київ", description="City name for DTEK API lookup (default: 'Київ')")
):
    """
    Returns a dictionary of streets and house statuses in the rectangle specified by top-left and bottom-right points.
    """
    # Validate coordinate inputs
    for lat_val in (lat_top, lat_bottom):
        if not (-90.0 <= lat_val <= 90.0):
            raise InvalidInputError(f"Latitude coordinate {lat_val} must be between -90 and 90 degrees")
            
    for lon_val in (lon_left, lon_right):
        if not (-180.0 <= lon_val <= 180.0):
            raise InvalidInputError(f"Longitude coordinate {lon_val} must be between -180 and 180 degrees")

    logger.info(f"Viewport DTEK outage scan: top-left({lat_top},{lon_left}), bottom-right({lat_bottom},{lon_right}), dso={dsoId}, city={city}")
    
    return await dtek_service.get_viewport_outages(
        lat_top=lat_top,
        lon_left=lon_left,
        lat_bottom=lat_bottom,
        lon_right=lon_right,
        dso_id=dsoId,
        city=city
    )
