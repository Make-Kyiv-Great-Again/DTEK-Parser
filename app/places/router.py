import logging
from typing import List
from fastapi import APIRouter, Query
from app.places.service import places_service
from app.places.schemas import PlaceResponse
from app.core.exceptions import InvalidInputError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

@router.get("/nearby", response_model=List[PlaceResponse], summary="Search nearby amenities and shops")
async def get_nearby_places(
    lat: float = Query(..., description="Latitude coordinate (-90 to 90)"),
    lng: float = Query(..., description="Longitude coordinate (-180 to 180)"),
    radius: int = Query(500, description="Search radius in meters (positive integer)")
):
    """Searches for cafes, restaurants, fast foods, pubs, and shops near the given coordinate."""
    # Input validation
    if not (-90.0 <= lat <= 90.0):
        raise InvalidInputError("Latitude must be between -90 and 90 degrees")
    if not (-180.0 <= lng <= 180.0):
        raise InvalidInputError("Longitude must be between -180 and 180 degrees")
    if radius <= 0:
        raise InvalidInputError("Radius must be a positive integer greater than 0")

    logger.info(f"Received nearby search: lat={lat}, lng={lng}, radius={radius}")
    return await places_service.get_nearby_places(lat, lng, radius)
