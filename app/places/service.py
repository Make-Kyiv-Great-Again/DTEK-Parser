import logging
from typing import List, Dict, Any
from app.places.client import overpass_client
from app.places.schemas import PlaceResponse

logger = logging.getLogger(__name__)

class PlacesService:
    async def get_nearby_places(self, lat: float, lng: float, radius: int) -> List[PlaceResponse]:
        """Fetches and structures nearby amenities and shops from the Overpass client."""
        raw_data = await overpass_client.fetch_nearby_nodes(lat, lng, radius)
        elements = raw_data.get("elements", [])

        places = []
        for el in elements:
            el_id = el.get("id")
            el_lat = el.get("lat")
            el_lng = el.get("lon")
            tags = el.get("tags", {})

            if not el_id or el_lat is None or el_lng is None:
                continue

            # Determine place type from amenity or shop tag
            place_type = tags.get("amenity") or tags.get("shop") or "unknown"
            name = tags.get("name") or tags.get("name:uk") or tags.get("name:en") or "Без назви"

            # Filter metadata: include all tags except primary mapping keys
            metadata = {k: v for k, v in tags.items() if k not in ("name", "name:uk", "name:en", "amenity", "shop")}

            places.append(PlaceResponse(
                id=el_id,
                type=place_type,
                lat=el_lat,
                lng=el_lng,
                name=name,
                metadata=metadata
            ))

        return places

places_service = PlacesService()
