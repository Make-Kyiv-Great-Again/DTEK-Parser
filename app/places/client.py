import logging
import os
import httpx
import asyncio
from app.core.config import settings
from app.core.exceptions import ClientConnectionError, ClientResponseError

logger = logging.getLogger(__name__)

class OverpassClient:
    def __init__(self):
        self.base_url = os.getenv("OVERPASS_INTERNAL_URL", "http://local_overpass/api/interpreter")
        self.timeout = settings.TIMEOUT_SECONDS

    async def fetch_nearby_nodes(self, lat: float, lng: float, radius: int) -> dict:
        """Queries the local Overpass instance for shops and food amenities within a radius."""
        query = f"""[out:json];
(
  node(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|fast_food|pub"];
  node(around:{radius},{lat},{lng})["shop"];
);
out body;"""

        max_attempts = 3
        for attempt in range(max_attempts):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    logger.debug(f"Sending Overpass QL query: {query}")
                    # Standard form-encoded POST request
                    response = await client.post(self.base_url, data={"data": query})
                    
                    if response.status_code == 404:
                        raise ClientResponseError(
                            "Overpass interpreter URL not found (404)",
                            status_code=404
                        )
                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException as e:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    logger.error(f"Timeout connecting to local Overpass container: {e}")
                    raise ClientConnectionError(
                        "Gateway Timeout: Request to Overpass container timed out"
                    ) from e
                except httpx.HTTPStatusError as e:
                    if response.status_code >= 500 and attempt < max_attempts - 1:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    logger.error(f"Overpass returned status code {response.status_code}: {response.text}")
                    raise ClientResponseError(
                        f"Bad Gateway: Overpass container returned {response.status_code}",
                        status_code=response.status_code
                    ) from e
                except httpx.RequestError as e:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    logger.error(f"Failed connecting to local Overpass container: {e}")
                    raise ClientConnectionError(
                        "Bad Gateway: Failed to connect to Overpass container"
                    ) from e
                except ValueError as e:
                    logger.error(f"Overpass response parsing failed: {e}")
                    raise ClientResponseError(
                        "Bad Gateway: Overpass returned invalid JSON response",
                        status_code=502
                    ) from e

        raise ClientConnectionError("Failed to reach Overpass container after retries")

overpass_client = OverpassClient()
