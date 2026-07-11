import json
import logging
import time
from typing import Optional, Any
from collections import OrderedDict
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis library is not installed. Caching will fall back to in-memory dictionary.")


class LRUMemoryCache:
    """A size-capped in-memory cache with TTL support (LRU policy)."""
    def __init__(self, maxsize: int = 1000):
        self.cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        entry = self.cache[key]
        if entry["expire_at"] is not None and entry["expire_at"] < time.time():
            del self.cache[key]
            return None
        self.cache.move_to_end(key)
        return entry["value"]

    def set(self, key: str, value: Any, expire_seconds: Optional[int] = None):
        # Evict oldest if full
        if len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        expire_at = (time.time() + expire_seconds) if expire_seconds else None
        self.cache[key] = {
            "value": value,
            "expire_at": expire_at
        }
        self.cache.move_to_end(key)


class CacheService:
    def __init__(self):
        self.redis_client = None
        self.memory_cache = LRUMemoryCache(maxsize=1000)
        self.redis_url = settings.REDIS_URL
        self._initialized = False

    async def _init_redis(self):
        """Lazily initialize Redis connection pool asynchronously."""
        if self._initialized:
            return
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self.redis_client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0
                )
                logger.info("Redis cache asynchronously initialized.")
            except Exception as e:
                logger.error(f"Failed to connect to Redis at {self.redis_url}: {e}. Using in-memory fallback.")
                self.redis_client = None
        self._initialized = True

    async def get(self, key: str) -> Optional[Any]:
        await self._init_redis()
        if self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val:
                    logger.debug(f"Redis hit for key: {key}")
                    return json.loads(val)
                logger.debug(f"Redis miss for key: {key}")
            except Exception as e:
                logger.warning(f"Redis get error: {e}. Falling back to in-memory.")

        # Check memory cache fallback
        val = self.memory_cache.get(key)
        if val is not None:
            logger.debug(f"Memory cache hit for key: {key}")
            return val
        logger.debug(f"Memory cache miss for key: {key}")
        return None

    async def set(self, key: str, value: Any, expire_seconds: int = None) -> bool:
        await self._init_redis()
        if self.redis_client:
            try:
                serialized = json.dumps(value)
                if expire_seconds:
                    await self.redis_client.setex(key, expire_seconds, serialized)
                else:
                    await self.redis_client.set(key, serialized)
                logger.debug(f"Redis set key: {key}")
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}. Falling back to in-memory.")

        self.memory_cache.set(key, value, expire_seconds)
        logger.debug(f"Memory cache set key: {key}")
        return True

    async def close(self):
        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")


cache_service = CacheService()
