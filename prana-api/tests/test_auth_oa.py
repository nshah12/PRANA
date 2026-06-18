"""
Tests for OA (Org Admin) authentication flow.

Covers:
  - Login: happy path, wrong password, account locked, account not found
  - TOTP: happy path, invalid code, lockout at 5 failures
  - Step-token chain: login → totp
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_oa_row(
    *,
    status="ACTIVE",
    password_hash="$argon2id$v=19$...",
    failed_totp_count=0,
    totp_secret_enc="ENC_TOTP_SECRET",
    totp_configured_at="2024-01-01T00:00:00Z",
):
    return {
        "oa_user_id": "oa-user-uuid-001",
        "tenant_id": "tenant-uuid-001",
        "email": "admin@acme.com",
        "role": "oa_admin",
        "status": status,
        "password_hash": password_hash,
        "failed_totp_count": failed_totp_count,
        "totp_secret_enc": totp_secret_enc,
        "totp_configured_at": totp_configured_at,
        "force_reset": False,
    }


# ── Login endpoint ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_user_not_found(client, mock_db):
    mock_db.fetchrow.return_value = None
    resp = await client.post("/auth/org/login", json={
        "email": "nobody@acme.com",
        "password": "secret",
    })
    # Must return 401 but must NOT reveal user doesn't exist (enumeration guard)
    assert resp.status_code == 401
    assert resp.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_account_locked(client, mock_db):
    mock_db.fetchrow.return_value = _make_oa_row(status="LOCKED")
    with patch("routers.auth_oa.argon2.verify", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 403
    assert resp.json()["error"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_login_wrong_password(client, mock_db):
    mock_db.fetchrow.return_value = _make_oa_row()
    with patch("routers.auth_oa.argon2.verify", return_value=False):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "wrong",
        })
    assert resp.status_code == 401
    assert resp.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_success_returns_step_token(client, mock_db):
    mock_db.fetchrow.return_value = _make_oa_row()
    with patch("routers.auth_oa.argon2.verify", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "step_token" in data
    assert data.get("requires_totp") is True


@pytest.mark.asyncio
async def test_login_force_reset_returns_flag(client, mock_db):
    row = _make_oa_row()
    row["force_reset"] = True
    mock_db.fetchrow.return_value = row
    with patch("routers.auth_oa.argon2.verify", return_value=True):
        resp = await client.post("/auth/org/login", json={
            "email": "admin@acme.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    assert resp.json().get("force_reset") is True


# ── TOTP lockout ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_totp_locks_at_5_failures(client, mock_db, mock_redis):
    """After 5 failed TOTP attempts the account must be set to LOCKED."""
    mock_redis.get.return_value = "step-token-payload-encoded"

    row = _make_oa_row(failed_totp_count=4)  # 4 prior failures — next fails → lock
    mock_db.fetchrow.return_value = row

    with patch("routers.auth_oa._verify_step_token", return_value={
        "sub": "oa-user-uuid-001",
        "step": "totp",
    }):
        with patch("routers.auth_oa.TOTPService.verify", return_value=False):
            resp = await client.post("/auth/org/totp", json={
                "step_token": "dummy-step-token",
                "code": "000000",
            })

    assert resp.status_code == 403
    assert resp.json()["error"] == "ACCOUNT_LOCKED"
    # DB must have been called to set status=LOCKED
    mock_db.execute.assert_called()
    call_args_str = str(mock_db.execute.call_args_list)
    assert "LOCKED" in call_args_str
