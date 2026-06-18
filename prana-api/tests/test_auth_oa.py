"""
Tests for OA (Org Admin) authentication flow.

Covers:
  - Login: happy path, wrong password, account locked, account not found
  - TOTP: happy path, invalid code, lockout at 5 failures
  - Step-token chain: login → totp
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_oa_row(
    *,
    status="ACTIVE",
    password_hash="$argon2id$v=19$...",
    temp_password_hash=None,
    failed_totp_count=0,
    totp_secret_enc="ENC_TOTP_SECRET",
    totp_configured_at="2024-01-01T00:00:00Z",
    force_reset=False,
):
    return {
        "oa_user_id": "oa-user-uuid-001",
        "tenant_id": "tenant-uuid-001",
        "email": "admin@acme.com",
        "role": "oa_admin",
        "status": status,
        "password_hash": password_hash,
        "temp_password_hash": temp_password_hash,
        "failed_totp_count": failed_totp_count,
        "totp_secret_enc": totp_secret_enc,
        "totp_configured_at": totp_configured_at,
        "force_reset": force_reset,
    }


# ── Login endpoint ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_user_not_found(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = None
    resp = await client.post("/auth/org/login", json={
        "email": "nobody@acme.com",
        "password": "secret",
    })
    assert resp.status_code == 401
    # Must NOT reveal user doesn't exist — enumeration guard
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_account_locked(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _make_oa_row(status="LOCKED")
    with patch("routers.auth_oa.verify_password", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_login_wrong_password(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _make_oa_row()
    with patch("routers.auth_oa.verify_password", return_value=False):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "wrong",
        })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_success_returns_step_token(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _make_oa_row()
    mock_redis.setex = AsyncMock()
    with patch("routers.auth_oa.verify_password", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "step_token" in data
    assert data.get("requires_totp") is True


@pytest.mark.asyncio
async def test_login_force_reset_returns_flag(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _make_oa_row(force_reset=True)
    mock_redis.setex = AsyncMock()
    with patch("routers.auth_oa.verify_password", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("requires_password_reset") is True
    assert "step_token" in data


# ── TOTP lockout ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_totp_locks_at_5_failures(client, mock_db, mock_redis):
    """After 5 failed TOTP attempts the account must be set to LOCKED."""
    step_payload = b"oa-user-uuid-001:tenant-uuid-001:oa_admin"
    mock_redis.get = AsyncMock(return_value=step_payload)
    mock_redis.delete = AsyncMock()

    # fetchrow for oa_user row (totp step), then fetchrow for platform_config (lock threshold)
    def _fetchrow_side(*args, **kwargs):
        sql = args[0].lower() if args else ""
        if "platform_config" in sql:
            return None   # use default threshold = 5
        return _make_oa_row(failed_totp_count=4)  # 4 prior → next = lock

    mock_db.fetchrow = AsyncMock(side_effect=_fetchrow_side)
    mock_db.execute = AsyncMock()

    with patch("routers.auth_oa.TOTPService.verify", return_value=False):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy-step-token",
            "code": "000000",
        })

    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_LOCKED"
    # DB must have been called to set status=LOCKED
    mock_db.execute.assert_called()
    call_args_str = str(mock_db.execute.call_args_list)
    assert "LOCKED" in call_args_str


@pytest.mark.asyncio
async def test_totp_wrong_code_below_lockout(client, mock_db, mock_redis):
    """1 failed TOTP attempt — account not yet locked, returns 401."""
    step_payload = b"oa-user-uuid-001:tenant-uuid-001:oa_admin"
    mock_redis.get = AsyncMock(return_value=step_payload)
    mock_redis.delete = AsyncMock()

    def _fetchrow_side(*args, **kwargs):
        sql = args[0].lower() if args else ""
        if "platform_config" in sql:
            return None
        return _make_oa_row(failed_totp_count=1)

    mock_db.fetchrow = AsyncMock(side_effect=_fetchrow_side)
    mock_db.execute = AsyncMock()

    with patch("routers.auth_oa.TOTPService.verify", return_value=False):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy-step-token",
            "code": "999999",
        })

    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_TOTP"


@pytest.mark.asyncio
async def test_login_suspended_account_rejected(client, mock_db, mock_redis):
    """SUSPENDED accounts must be blocked (not just LOCKED)."""
    mock_db.fetchrow.return_value = _make_oa_row(status="SUSPENDED")
    with patch("routers.auth_oa.verify_password", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_INACTIVE"
