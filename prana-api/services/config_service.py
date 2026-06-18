import json
from typing import Optional
import asyncpg
import redis.asyncio as redis


class ConfigService:
    """
    Resolves runtime config: tenant_config overrides platform_config.
    Changes apply to NEW workflow instances only — running instances use the value at start time.
    Results are cached in Redis with a 5-minute TTL.
    """

    def __init__(self, db: asyncpg.Connection, redis_client: redis.Redis, cache_ttl: int = 300):
        self._db = db
        self._redis = redis_client
        self._ttl = cache_ttl

    async def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[str]:
        cache_key = f"cfg:{tenant_id or 'platform'}:{key}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return cached.decode()

        value = await self._resolve(key, tenant_id)
        if value is not None:
            await self._redis.setex(cache_key, self._ttl, value)
        return value

    async def get_int(self, key: str, tenant_id: Optional[str] = None) -> Optional[int]:
        val = await self.get(key, tenant_id)
        return int(val) if val is not None else None

    async def get_bool(self, key: str, tenant_id: Optional[str] = None) -> Optional[bool]:
        val = await self.get(key, tenant_id)
        return val.lower() == "true" if val is not None else None

    async def invalidate(self, key: str, tenant_id: Optional[str] = None) -> None:
        """Call after OA-Admin or PA updates a config value."""
        cache_key = f"cfg:{tenant_id or 'platform'}:{key}"
        await self._redis.delete(cache_key)

    async def _resolve(self, key: str, tenant_id: Optional[str]) -> Optional[str]:
        if tenant_id:
            row = await self._db.fetchrow(
                """
                SELECT COALESCE(
                  (SELECT config_value FROM tenant_config   WHERE tenant_id = $1 AND config_key = $2),
                  (SELECT config_value FROM platform_config WHERE config_key = $2)
                ) AS resolved_value
                """,
                tenant_id, key,
            )
        else:
            row = await self._db.fetchrow(
                "SELECT config_value AS resolved_value FROM platform_config WHERE config_key = $1",
                key,
            )
        return row["resolved_value"] if row else None
