"""
Server-side Redis cache with automatic invalidation.

Usage:
    from lib.cache import cache_get, cache_set, cache_invalidate, cached_route

Pattern:  read → cache-miss → DB → cache_set → return
          write → DB → cache_invalidate(prefix) → return

Keys are namespaced:  prana:{namespace}:{scope}
"""
import json
import functools
import logging
from typing import Any, Callable, Optional
import redis.asyncio as aioredis
from config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis


async def cache_get(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache_get failed key=%s err=%s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    try:
        await get_redis().setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("cache_set failed key=%s err=%s", key, exc)


async def cache_invalidate(pattern: str) -> int:
    """Delete all keys matching the glob pattern. Returns count deleted."""
    try:
        r = get_redis()
        keys = await r.keys(pattern)
        if keys:
            return await r.delete(*keys)
        return 0
    except Exception as exc:
        logger.warning("cache_invalidate failed pattern=%s err=%s", pattern, exc)
        return 0


def cached(namespace: str, ttl: int = 60, scope_arg: str | None = None):
    """
    Decorator for async FastAPI path functions.

    namespace   — prefix, e.g. "tenants", "platform_config"
    ttl         — seconds to keep in cache (default 60)
    scope_arg   — name of a path/query param whose value is appended to key,
                  e.g. scope_arg="tenant_id" → key prana:{namespace}:{tenant_id value}

    Cache key format:  prana:{namespace}:{scope_value or "global"}
    To invalidate a namespace:  await cache_invalidate("prana:{namespace}:*")
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            scope = kwargs.get(scope_arg, "global") if scope_arg else "global"
            key = f"prana:{namespace}:{scope}"

            cached_val = await cache_get(key)
            if cached_val is not None:
                logger.debug("cache_hit key=%s", key)
                return cached_val

            result = await fn(*args, **kwargs)

            await cache_set(key, result, ttl=ttl)
            logger.debug("cache_set key=%s ttl=%d", key, ttl)
            return result
        return wrapper
    return decorator


# Convenience invalidation helpers
async def invalidate_tenants() -> None:
    await cache_invalidate("prana:tenants:*")

async def invalidate_platform_config() -> None:
    await cache_invalidate("prana:platform_config:*")

async def invalidate_tenant_config(tenant_id: str) -> None:
    await cache_invalidate(f"prana:tenant_config:{tenant_id}")
