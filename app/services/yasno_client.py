import logging
import httpx
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

class YasnoClient:
    def __init__(self):
        self.base_url = settings.YASNO_BASE_URL
        self.timeout = settings.TIMEOUT_SECONDS

    async def _request(self, method: str, path: str, params: dict = None) -> any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(method, url, params=params)
                if response.status_code == 404:
                    logger.warning(f"Yasno API returned 404 for {url} with params {params}")
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Resource not found at Yasno API: {path}"
                    )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(f"Yasno API timeout for {url}: {str(e)}")
                raise HTTPException(
                    status_code=504, 
                    detail="Gateway Timeout: Yasno API request timed out"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"Yasno API HTTP error {response.status_code} for {url}: {e.response.text}")
                raise HTTPException(
                    status_code=502, 
                    detail=f"Bad Gateway: Yasno API returned status code {response.status_code}"
                )
            except httpx.RequestError as e:
                logger.error(f"Yasno API request error for {url}: {str(e)}")
                raise HTTPException(
                    status_code=502, 
                    detail="Bad Gateway: Failed to connect to Yasno API"
                )
            except ValueError as e:
                logger.error(f"Yasno API returned invalid JSON: {str(e)}")
                raise HTTPException(
                    status_code=502, 
                    detail="Bad Gateway: Yasno API returned invalid JSON structure"
                )

    async def fetch_regions(self) -> list:
        """Fetch all available regions and their DSOs."""
        return await self._request("GET", "public/shutdowns/addresses/v2/regions")

    async def search_streets(self, region_id: int, query: str, dso_id: int) -> list:
        """Search for streets by region, query string, and DSO ID."""
        params = {
            "regionId": region_id,
            "query": query,
            "dsoId": dso_id
        }
        return await self._request("GET", "public/shutdowns/addresses/v2/streets", params=params)

    async def search_houses(self, region_id: int, street_id: int, query: str, dso_id: int) -> list:
        """Search for houses on a street matching the query prefix."""
        params = {
            "regionId": region_id,
            "streetId": street_id,
            "query": query,
            "dsoId": dso_id
        }
        return await self._request("GET", "public/shutdowns/addresses/v2/houses", params=params)

    async def fetch_house_group(self, region_id: int, street_id: int, house_id: int, dso_id: int) -> dict:
        """Fetch the group and subgroup for a specific house address."""
        params = {
            "regionId": region_id,
            "streetId": street_id,
            "houseId": house_id,
            "dsoId": dso_id
        }
        return await self._request("GET", "public/shutdowns/addresses/v2/group", params=params)

    async def fetch_planned_outages(self, region_id: int, dso_id: int) -> dict:
        """Fetch planned outages for a region and DSO."""
        path = f"public/shutdowns/regions/{region_id}/dsos/{dso_id}/planned-outages"
        return await self._request("GET", path)

    async def fetch_probable_outages(self, region_id: int, dso_id: int) -> dict:
        """Fetch the weekly recurring (probable) outages schedule for a region and DSO."""
        params = {
            "regionId": region_id,
            "dsoId": dso_id
        }
        return await self._request("GET", "public/shutdowns/probable-outages", params=params)

yasno_client = YasnoClient()
