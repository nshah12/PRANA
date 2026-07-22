import base64
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import jwt as pyjwt
import redis.asyncio as redis

from config import Settings


def _b64url(data: bytes) -> str:
    """URL-safe base64 without padding — the JWS segment encoding (RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class JWTService:
    """
    RS256 JWT issue and verification.
    - JTI = session_id — checked against Redis blocklist on every request.
    - Signing: local PEM in dev/test; KMS (private key never leaves the HSM) in production.
    - Refresh tokens are opaque random bytes stored as SHA-256 hash in user_session.
    """

    def __init__(self, settings: Settings, redis_client: redis.Redis, kms_service=None):
        self._settings = settings
        self._redis = redis_client
        self._kms = kms_service
        self._public_key = Path(settings.jwt_public_key_path).read_text()
        # Local PEM for non-production (dev/test/staging-local). Production signs via KMS.
        self._private_key = (
            None if settings.is_production
            else Path(settings.jwt_private_key_path).read_text()
        )

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
        # Dev/test: sign locally.
        if self._private_key:
            return pyjwt.encode(payload, self._private_key, algorithm="RS256")
        # Production: sign via KMS so the private key never leaves the HSM.
        if self._kms and self._settings.jwt_kms_key_id:
            return self._sign_via_kms(payload)
        raise RuntimeError(
            "No JWT signing key available: set jwt_private_key_path (dev) "
            "or jwt_kms_key_id + KMS service (prod)."
        )

    def _sign_via_kms(self, payload: dict) -> str:
        """Build an RS256 JWS whose signature is produced by KMS (RSASSA_PKCS1_V1_5_SHA_256)."""
        header = {"alg": "RS256", "typ": "JWT"}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(payload, separators=(",", ":")).encode())
        )
        signature = self._kms.sign_jwt(signing_input.encode(), self._settings.jwt_kms_key_id)
        return signing_input + "." + _b64url(signature)

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
