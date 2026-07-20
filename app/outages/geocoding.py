import logging
import os
import httpx
from typing import Dict, Any
from app.core.exceptions import GeocodingError, AddressNotFoundError
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeocodingService:
    def __init__(self):
        self.base_url = os.getenv("OVERPASS_INTERNAL_URL", "http://local_overpass/api/interpreter")
        self.timeout = settings.TIMEOUT_SECONDS
        self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def reverse_geocode(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Reverse geocodes coordinates to street, house, region, and dso id using the local Overpass instance.
        """
        query = f"""[out:json];
(
  node(around:150,{lat},{lon})["addr:housenumber"]["addr:street"];
  way(around:150,{lat},{lon})["addr:housenumber"]["addr:street"];
);
out center;"""

        try:
            client = self._get_client()
            logger.debug(f"Sending geocoding query to local Overpass: {query}")
            response = await client.post(self.base_url, data={"data": query})
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            err_msg = f"Failed to connect to local Overpass container for geocoding: {e}"
            logger.error(err_msg)
            raise GeocodingError(err_msg)

        elements = data.get("elements", [])
        if not elements:
            raise AddressNotFoundError("Не вдалося визначити адресу за цими координатами у базі даних.")

        # Find the closest element using simple Euclidean distance
        closest_element = None
        min_distance = float("inf")

        for el in elements:
            # Nodes have lat/lon directly; Ways/Relations with "out center" have a "center" dict containing lat/lon
            el_lat = el.get("lat") or el.get("center", {}).get("lat")
            el_lon = el.get("lon") or el.get("center", {}).get("lon")
            if el_lat is None or el_lon is None:
                continue

            distance_sq = (el_lat - lat) ** 2 + (el_lon - lon) ** 2
            if distance_sq < min_distance:
                min_distance = distance_sq
                closest_element = el

        if not closest_element:
            raise AddressNotFoundError("Не вдалося знайти будівлю з адресою поруч з вказаними координатами.")

        address_tags = closest_element.get("tags", {})
        street_name = address_tags.get("addr:street")
        house_number = address_tags.get("addr:housenumber", "1")

        if not street_name:
            raise AddressNotFoundError("Не вдалося знайти назву вулиці для найближчої будівлі.")

        # Determine region and DSO ID by coordinate boundaries (Kyiv vs Dnipro)
        region_id = 25  # Kyiv
        dso_id = 902   # DTEK Kyiv Grids

        if lat <= 49.5:
            # Dnipro (latitude ~48.46)
            region_id = 3
            dso_id = 301

        logger.info(f"Resolved coordinate {lat},{lon} to local address: {street_name}, {house_number} (Region: {region_id})")

        return {
            "street_name": street_name,
            "house_number": house_number,
            "region_id": region_id,
            "dso_id": dso_id
        }

geocoding_service = GeocodingService()
