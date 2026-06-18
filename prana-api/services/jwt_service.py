import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import jwt as pyjwt
import redis.asyncio as redis

from config import Settings


class JWTService:
    """
    RS256 JWT issue and verification.
    - JTI = session_id — checked against Redis blocklist on every request.
    - Private key signing: KMS in production, local PEM in dev.
    - Refresh tokens are opaque random bytes stored as SHA-256 hash in user_session.
    """

    def __init__(self, settings: Settings, redis_client: redis.Redis):
        self._settings = settings
        self._redis = redis_client
        self._public_key = Path(settings.jwt_public_key_path).read_text()
        # Dev only — in prod, signing happens via KMSService.sign_jwt
        self._private_key = Path(settings.jwt_private_key_path).read_text() \
            if settings.app_env == "development" else None

    def issue(
        self,
        *,
        user_type: str,        # employee | oa_user | portal_admin
        user_id: str,
        tenant_id: Optional[str],
        role: Optional[str],
        session_id: str,
        ttl_minutes: int = 60,
    ) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "iss": self._settings.jwt_issuer,
            "sub": user_id,
            "jti": session_id,              # JTI = session_id for O(1) revocation
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
            "user_type": user_type,
            "tenant_id": tenant_id,
            "role": role,
        }
        if self._private_key:
            return pyjwt.encode(payload, self._private_key, algorithm="RS256")
        raise RuntimeError("KMS signing not implemented yet — set app_env=development for local keys")

    def decode(self, token: str) -> dict:
        """Decode and verify RS256 JWT. Raises pyjwt.InvalidTokenError on any failure."""
        return pyjwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            issuer=self._settings.jwt_issuer,
            options={"require": ["exp", "iat", "jti", "sub", "user_type"]},
        )

    async def is_revoked(self, session_id: str) -> bool:
        """Check Redis blocklist. O(1). Key: revoked:{session_id}"""
        return await self._redis.exists(f"revoked:{session_id}") == 1

    async def revoke(self, session_id: str, ttl_seconds: int = 3600 * 24 * 7) -> None:
        """
        Add session to Redis blocklist.
        TTL = refresh_token_ttl_days so key auto-expires when no refresh possible.
        """
        await self._redis.setex(f"revoked:{session_id}", ttl_seconds, "1")
