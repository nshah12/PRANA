import random
import string
from typing import Optional

import redis.asyncio as redis

from config import get_settings

# Redis namespaces (no plaintext NIK ever used as key)
# otp:{purpose}:{pan_token}  → 6-digit code, TTL = per purpose
_PREFIX = "otp"

# Dev-only bypass OTP — accepted in addition to the real OTP when debug=True.
# NEVER active in production (settings.debug is False by default).
_DEV_BYPASS_OTP = "123456"


class OTPService:
    """
    Generates and verifies time-limited numeric OTPs stored in Redis.
    Key is always pan_token — never mobile number or PAN directly.
    """

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def generate(
        self,
        purpose: str,        # LOGIN | ACTIVATION | SHARE_ACCESS | PASSWORD_RESET
        pan_token: str,
        ttl_seconds: int = 600,
    ) -> str:
        code = "".join(random.choices(string.digits, k=6))
        key = f"{_PREFIX}:{purpose}:{pan_token}"
        # Store with attempt counter alongside: "code:attempts"
        await self._redis.setex(key, ttl_seconds, f"{code}:0")
        return code

    async def verify(self, purpose: str, pan_token: str, code: str) -> bool:
        # Dev bypass — only when sms_provider="dev" (console logging mode, never production)
        if get_settings().sms_provider == "dev" and code == _DEV_BYPASS_OTP:
            # Consume the real OTP from Redis if one exists, so it can't be reused
            await self._redis.delete(f"{_PREFIX}:{purpose}:{pan_token}")
            return True

        key = f"{_PREFIX}:{purpose}:{pan_token}"
        raw = await self._redis.get(key)
        if not raw:
            return False

        stored_code, attempts = raw.decode().split(":")
        attempts = int(attempts)

        if attempts >= 3:
            await self._redis.delete(key)
            return False

        if stored_code != code:
            await self._redis.setex(
                key,
                await self._redis.ttl(key),
                f"{stored_code}:{attempts + 1}",
            )
            return False

        await self._redis.delete(key)
        return True

    async def invalidate(self, purpose: str, pan_token: str) -> None:
        await self._redis.delete(f"{_PREFIX}:{purpose}:{pan_token}")
