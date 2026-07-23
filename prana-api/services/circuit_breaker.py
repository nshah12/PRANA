"""
Circuit breaker for outbound channel vendors (Email/SMS/WhatsApp/IVR).

Redis-backed so state is shared across every pod/consumer instance — the same
mechanism this codebase already uses for JWT revocation and rate limiting,
not a new one (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4).

Two keys per (channel, vendor):
  circuit:{channel}:{vendor}:failures  — INCR'd on each failure, expires after
                                          open_seconds so old failures don't
                                          linger forever once below threshold
  circuit:{channel}:{vendor}:open      — SETEX'd once failures hit the
                                          threshold; its own TTL is the open
                                          duration, so the breaker self-clears
                                          with no separate sweep job needed

Threshold/duration are read from platform_config/tenant_config
(comm_circuit_breaker_failure_threshold / comm_circuit_breaker_open_seconds)
via the existing ConfigService — never hardcoded. The literal fallbacks below
only apply if those keys are somehow unseeded; in every real deployment
schema.sql seeds them.
"""
from typing import Optional

import redis.asyncio as redis

from services.config_service import ConfigService

_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_OPEN_SECONDS = 60


class CircuitBreaker:
    def __init__(self, redis_client: redis.Redis, config: ConfigService) -> None:
        self._redis = redis_client
        self._config = config

    async def is_open(self, channel: str, vendor: str) -> bool:
        return bool(await self._redis.exists(self._open_key(channel, vendor)))

    async def record_failure(self, channel: str, vendor: str, tenant_id: Optional[str] = None) -> None:
        threshold = await self._config.get_int("comm_circuit_breaker_failure_threshold", tenant_id) \
            or _DEFAULT_FAILURE_THRESHOLD
        open_seconds = await self._config.get_int("comm_circuit_breaker_open_seconds", tenant_id) \
            or _DEFAULT_OPEN_SECONDS

        count_key = self._failures_key(channel, vendor)
        count = await self._redis.incr(count_key)
        if count == 1:
            await self._redis.expire(count_key, open_seconds)

        if count >= threshold:
            await self._redis.setex(self._open_key(channel, vendor), open_seconds, "1")
            await self._redis.delete(count_key)

    async def record_success(self, channel: str, vendor: str) -> None:
        await self._redis.delete(self._failures_key(channel, vendor))
        await self._redis.delete(self._open_key(channel, vendor))

    def _failures_key(self, channel: str, vendor: str) -> str:
        return f"circuit:{channel}:{vendor}:failures"

    def _open_key(self, channel: str, vendor: str) -> str:
        return f"circuit:{channel}:{vendor}:open"
