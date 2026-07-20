import logging
import httpx
from app.core.config import settings
from app.core.exceptions import ClientConnectionError, ClientResponseError

logger = logging.getLogger(__name__)

class YasnoClient:
    def __init__(self):
        self.base_url = settings.YASNO_BASE_URL
        self.timeout = settings.TIMEOUT_SECONDS
        self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, params: dict = None) -> any:
        import asyncio
        url = f"{self.base_url}/{path.lstrip('/')}"
        
        max_attempts = 3
        client = self._get_client()
        for attempt in range(max_attempts):
            try:
                response = await client.request(method, url, params=params)
                if response.status_code == 404:
                    logger.warning(f"Yasno API returned 404 for {url} with params {params}")
                    raise ClientResponseError(
                        f"Resource not found at Yasno API: {path}",
                        status_code=404
                    )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.warning(f"Yasno API timeout for {url}: {str(e)}")
                raise ClientConnectionError(
                    "Gateway Timeout: Yasno API request timed out"
                ) from e
            except httpx.HTTPStatusError as e:
                if response.status_code >= 500 and attempt < max_attempts - 1:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.warning(f"Yasno API HTTP error {response.status_code} for {url}: {e.response.text}")
                raise ClientResponseError(
                    f"Bad Gateway: Yasno API returned status code {response.status_code}",
                    status_code=response.status_code
                ) from e
            except httpx.RequestError as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.warning(f"Yasno API request error for {url}: {str(e)}")
                raise ClientConnectionError(
                    "Bad Gateway: Failed to connect to Yasno API"
                ) from e
            except ValueError as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.warning(f"Yasno API returned invalid JSON: {str(e)}")
                raise ClientResponseError(
                    "Bad Gateway: Yasno API returned invalid JSON structure"
                ) from e

    async def fetch_regions(self) -> list:
        """Fetch all available regions and their DSOs."""
        from app.core.cache import cache_service
        cache_key = "yasno:regions"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached
            
        data = await self._request("GET", "public/shutdowns/addresses/v2/regions")
        await cache_service.set(cache_key, data, expire_seconds=86400) # 24h
        return data

    async def search_streets(self, region_id: int, query: str, dso_id: int) -> list:
        """Search for streets by region, query string, and DSO ID."""
        from app.core.cache import cache_service
        cache_key = f"yasno:streets:{region_id}:{dso_id}:{query.lower().strip()}"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached
            
        params = {
            "regionId": region_id,
            "query": query,
            "dsoId": dso_id
        }
        data = await self._request("GET", "public/shutdowns/addresses/v2/streets", params=params)
        await cache_service.set(cache_key, data, expire_seconds=86400) # 24h
        return data

    async def search_houses(self, region_id: int, street_id: int, query: str, dso_id: int) -> list:
        """Search for houses on a street matching the query prefix."""
        from app.core.cache import cache_service
        cache_key = f"yasno:houses:{region_id}:{street_id}:{dso_id}:{query.lower().strip()}"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "regionId": region_id,
            "streetId": street_id,
            "query": query,
            "dsoId": dso_id
        }
        data = await self._request("GET", "public/shutdowns/addresses/v2/houses", params=params)
        await cache_service.set(cache_key, data, expire_seconds=86400) # 24h
        return data

    async def fetch_house_group(self, region_id: int, street_id: int, house_id: int, dso_id: int) -> dict:
        """Fetch the group and subgroup for a specific house address."""
        from app.core.cache import cache_service
        cache_key = f"yasno:house_group:{region_id}:{street_id}:{house_id}:{dso_id}"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "regionId": region_id,
            "streetId": street_id,
            "houseId": house_id,
            "dsoId": dso_id
        }
        data = await self._request("GET", "public/shutdowns/addresses/v2/group", params=params)
        await cache_service.set(cache_key, data, expire_seconds=86400) # 24h
        return data

    async def fetch_planned_outages(self, region_id: int, dso_id: int) -> dict:
        """Fetch planned outages for a region and DSO."""
        from app.core.cache import cache_service
        cache_key = f"yasno:planned_outages:{region_id}:{dso_id}"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached

        path = f"public/shutdowns/regions/{region_id}/dsos/{dso_id}/planned-outages"
        data = await self._request("GET", path)
        await cache_service.set(cache_key, data, expire_seconds=300) # 5 min
        return data

    async def fetch_probable_outages(self, region_id: int, dso_id: int) -> dict:
        """Fetch the weekly recurring (probable) outages schedule for a region and DSO."""
        from app.core.cache import cache_service
        cache_key = f"yasno:probable_outages:{region_id}:{dso_id}"
        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "regionId": region_id,
            "dsoId": dso_id
        }
        data = await self._request("GET", "public/shutdowns/probable-outages", params=params)
        await cache_service.set(cache_key, data, expire_seconds=3600) # 1 hour
        return data

yasno_client = YasnoClient()
