import json
import logging
from typing import Optional, Any
from app.config import settings

logger = logging.getLogger(__name__)

# Try to import redis
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis library is not installed. Caching will fall back to in-memory dictionary.")

class CacheService:
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}  # Fallback in-memory cache: { key: { "value": any, "expire_at": float } }
        self.redis_url = settings.REDIS_URL
        
        if REDIS_AVAILABLE and self.redis_url:
            try:
                # Initialize Redis connection pool
                self.redis_client = aioredis.from_url(
                    self.redis_url, 
                    encoding="utf-8", 
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0
                )
                logger.info(f"Redis cache initialized with URL: {self.redis_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis at {self.redis_url}: {e}. Falling back to in-memory caching.")
                self.redis_client = None

    async def get(self, key: str) -> Optional[Any]:
        if self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.warning(f"Redis get error: {e}. Falling back to in-memory.")
                
        # Check memory cache fallback
        import time
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if entry["expire_at"] is None or entry["expire_at"] > time.time():
                return entry["value"]
            else:
                del self.memory_cache[key]
        return None

    async def set(self, key: str, value: Any, expire_seconds: int = None) -> bool:
        if self.redis_client:
            try:
                serialized = json.dumps(value)
                if expire_seconds:
                    await self.redis_client.setex(key, expire_seconds, serialized)
                else:
                    await self.redis_client.set(key, serialized)
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}. Falling back to in-memory.")

        # Set memory cache fallback
        import time
        expire_at = (time.time() + expire_seconds) if expire_seconds else None
        self.memory_cache[key] = {
            "value": value,
            "expire_at": expire_at
        }
        return True

    async def close(self):
        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")

cache_service = CacheService()
