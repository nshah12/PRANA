"""Tests for services/jwt_service.py — real behavior against the local dev RS256
keypair, not source inspection.

Previously this file only ran inspect.getsource() and asserted on substrings —
it never instantiated JWTService, never signed/verified a real token, and never
exercised the Redis revoke()/is_revoked() round-trip. See test_jwt_kms_signing.py
for the production/KMS signing path, already covered separately.
"""
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest

from config import Settings
from services.jwt_service import JWTService


def _dev_service(redis_client=None) -> JWTService:
    """Real JWTService with the local dev PEM (app_env=test -> local key path)."""
    return JWTService(Settings(app_env="test"), redis_client or MagicMock())


# ── issue() / decode() round-trip ────────────────────────────────────────────

def test_issue_and_decode_round_trip():
    svc = _dev_service()
    token = svc.issue(
        user_type="oa_user", user_id="u-1", tenant_id="t-1",
        role="oa_admin", session_id="sess-1", ttl_minutes=5,
    )
    claims = svc.decode(token)

    assert claims["sub"] == "u-1"
    assert claims["jti"] == "sess-1"
    assert claims["tenant_id"] == "t-1"
    assert claims["role"] == "oa_admin"
    assert claims["user_type"] == "oa_user"


def test_issue_includes_jti_as_session_id_for_o1_revocation():
    svc = _dev_service()
    token = svc.issue(
        user_type="employee", user_id="emp-1", tenant_id="t-1",
        role=None, session_id="the-session-id", ttl_minutes=5,
    )
    assert svc.decode(token)["jti"] == "the-session-id"


def test_decode_rejects_expired_token():
    svc = _dev_service()
    token = svc.issue(
        user_type="oa_user", user_id="u-1", tenant_id="t-1",
        role="oa_admin", session_id="sess-1", ttl_minutes=-1,  # already expired
    )
    with pytest.raises(pyjwt.ExpiredSignatureError):
        svc.decode(token)


def test_decode_rejects_wrong_issuer():
    """A token signed with the real key but a forged issuer must not verify."""
    svc = _dev_service()
    forged_payload = {
        "iss": "not-prana.in", "sub": "u-1", "jti": "sess-1",
        "iat": 0, "exp": 9999999999, "user_type": "oa_user",
        "tenant_id": "t-1", "role": "oa_admin",
    }
    forged_token = pyjwt.encode(forged_payload, svc._private_key, algorithm="RS256")

    with pytest.raises(pyjwt.InvalidIssuerError):
        svc.decode(forged_token)


def test_decode_rejects_token_missing_required_claim():
    """options={'require': [...]} must actually be enforced, not just declared."""
    svc = _dev_service()
    incomplete_payload = {
        "iss": "prana.in", "sub": "u-1",
        "iat": 0, "exp": 9999999999, "user_type": "oa_user",
        # jti deliberately omitted
    }
    token = pyjwt.encode(incomplete_payload, svc._private_key, algorithm="RS256")

    with pytest.raises(pyjwt.MissingRequiredClaimError):
        svc.decode(token)


def test_decode_rejects_token_signed_with_a_different_key():
    """A token signed by an unrelated RSA key must fail RS256 signature verification,
    proving decode() actually checks the signature and doesn't just parse the JWT.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = other_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    svc = _dev_service()
    payload = {
        "iss": "prana.in", "sub": "u-1", "jti": "sess-1",
        "iat": 0, "exp": 9999999999, "user_type": "oa_user",
        "tenant_id": "t-1", "role": "oa_admin",
    }
    forged_token = pyjwt.encode(payload, other_key, algorithm="RS256")

    with pytest.raises(pyjwt.InvalidSignatureError):
        svc.decode(forged_token)


# ── is_revoked() / revoke() — real Redis interaction (mocked client) ───────

@pytest.mark.asyncio
async def test_is_revoked_checks_the_correct_redis_key():
    redis_client = MagicMock()
    redis_client.exists = AsyncMock(return_value=1)
    svc = _dev_service(redis_client)

    result = await svc.is_revoked("sess-1")

    assert result is True
    redis_client.exists.assert_awaited_once_with("revoked:sess-1")


@pytest.mark.asyncio
async def test_is_revoked_returns_false_when_key_absent():
    redis_client = MagicMock()
    redis_client.exists = AsyncMock(return_value=0)
    svc = _dev_service(redis_client)

    assert await svc.is_revoked("sess-1") is False


@pytest.mark.asyncio
async def test_revoke_sets_redis_blocklist_key_with_value():
    redis_client = MagicMock()
    redis_client.setex = AsyncMock()
    svc = _dev_service(redis_client)

    await svc.revoke("sess-1", ttl_seconds=3600)

    redis_client.setex.assert_awaited_once_with("revoked:sess-1", 3600, "1")


@pytest.mark.asyncio
async def test_revoke_defaults_ttl_to_seven_days():
    redis_client = MagicMock()
    redis_client.setex = AsyncMock()
    svc = _dev_service(redis_client)

    await svc.revoke("sess-1")

    redis_client.setex.assert_awaited_once_with("revoked:sess-1", 3600 * 24 * 7, "1")


@pytest.mark.asyncio
async def test_revoked_session_token_still_decodes_but_is_flagged_revoked():
    """decode() only verifies the JWS — revocation is a separate, deliberate check
    callers must perform via is_revoked(). This documents that division of
    responsibility rather than assuming decode() itself blocks revoked sessions.
    """
    redis_client = MagicMock()
    redis_client.setex = AsyncMock()
    redis_client.exists = AsyncMock(return_value=1)
    svc = _dev_service(redis_client)

    token = svc.issue(
        user_type="oa_user", user_id="u-1", tenant_id="t-1",
        role="oa_admin", session_id="sess-1", ttl_minutes=5,
    )
    await svc.revoke("sess-1")

    claims = svc.decode(token)          # still parses — decode() doesn't check revocation
    assert claims["jti"] == "sess-1"
    assert await svc.is_revoked(claims["jti"]) is True   # caller must check this separately
