"""Tests for TOTP one-time-use replay protection (Phase 2)."""
from unittest.mock import AsyncMock

import pytest

from services.totp_service import consume_totp_code


@pytest.mark.asyncio
async def test_first_use_allowed_replay_blocked():
    redis = AsyncMock()
    # Redis SET NX returns truthy on first set, None when the key already exists.
    redis.set = AsyncMock(side_effect=[True, None])
    assert await consume_totp_code(redis, "oa_user", "u1", "123456") is True
    assert await consume_totp_code(redis, "oa_user", "u1", "123456") is False


@pytest.mark.asyncio
async def test_uses_nx_and_ttl():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    await consume_totp_code(redis, "employee", "e9", "654321", ttl_seconds=90)
    _, kwargs = redis.set.call_args
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") == 90


@pytest.mark.asyncio
async def test_replayed_code_rejected_in_oa_flow(client, mock_db, mock_redis):
    """A valid OA TOTP code presented a second time (Redis says already-used) is rejected."""
    from unittest.mock import patch
    mock_redis.get = AsyncMock(return_value=b"oa-user-uuid-001:tenant-uuid-001:oa_admin")
    mock_redis.delete = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)  # code already used → replay

    def _fetchrow_side(*args, **kwargs):
        sql = args[0].lower() if args else ""
        if "platform_config" in sql:
            return None
        return {"totp_secret_enc": "ENC", "failed_totp_count": 0, "status": "ACTIVE"}

    mock_db.fetchrow = AsyncMock(side_effect=_fetchrow_side)
    mock_db.execute = AsyncMock()

    with patch("routers.auth_oa.TOTPService.verify", return_value=True):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy", "code": "000000",
        })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_TOTP"
