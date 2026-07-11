import logging
import httpx
from typing import Dict, Any
from app.core.exceptions import GeocodingError

logger = logging.getLogger(__name__)

class GeocodingService:
    def __init__(self):
        self.geocoder_urls = [
            "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1",
            "https://nominatim.openstreetmap.fr/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        ]
        self.headers = {
            "User-Agent": "SvitloLocatorApp/1.1 (contact: admin@svitlo-finder.xyz; educational wrapper API)"
        }

    async def reverse_geocode(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Reverse geocodes coordinates to street, house, region, and dso id.
        Returns a dict containing:
          - street_name: str
          - house_number: str
          - region_id: int
          - dso_id: int
        """
        geo_data = None
        last_err = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            for base_url in self.geocoder_urls:
                url = base_url.format(lat=lat, lon=lon)
                try:
                    r = await client.get(url, headers=self.headers)
                    r.raise_for_status()
                    data = r.json()
                    if data and "address" in data:
                        geo_data = data
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
            raise GeocodingError(err_msg)

        address = geo_data.get("address", {})
        
        house_number = address.get("house_number", "1")
        street_name = address.get("road") or address.get("street")
        if not street_name:
            raise GeocodingError("Road/street name could not be resolved from these coordinates.")

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

        return {
            "street_name": street_name,
            "house_number": house_number,
            "region_id": region_id,
            "dso_id": dso_id
        }

geocoding_service = GeocodingService()
