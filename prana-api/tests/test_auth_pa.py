"""
Tests for routers/auth_pa.py — Portal Admin auth flow.

Covers:
  - Login with @prana.in email + valid password returns {requires_totp, step_token}
  - Non-@prana.in email or wrong password → 401 (no domain hint)
  - TOTP lockout fires at 3 failures (stricter than OA's 5)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _make_pa_row(*, failed_totp_count: int = 0, status: str = "ACTIVE",
                 totp_configured_at=True):
    return {
        "pa_id": "pa-uuid-001",
        "password_hash": "argon2_hash_placeholder",
        "totp_configured_at": "2024-01-01T00:00:00Z" if totp_configured_at else None,
        "failed_totp_count": failed_totp_count,
        "status": status,
    }


# -- Login step 1 -----------------------------------------------------------

@pytest.mark.asyncio
async def test_pa_login_valid_credentials_returns_jwt(client, mock_db, mock_redis):
    """Valid @prana.in login returns {requires_totp: True, step_token}. No JWT issued here."""
    mock_db.fetchrow.return_value = _make_pa_row()

    with patch("routers.auth_pa.verify_password", return_value=True):
        resp = await client.post("/auth/admin/login", json={
            "email": "admin@prana.in",
            "password": "ValidPass@123",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("requires_totp") is True
    assert "step_token" in data and data["step_token"]

    # Redis must store pa_id for the step token (300s TTL)
    mock_redis.setex.assert_called_once()
    key_arg = mock_redis.setex.call_args[0][0]
    assert key_arg.startswith("pa_step:")


@pytest.mark.asyncio
async def test_pa_login_wrong_password_returns_401(client, mock_db, mock_redis):
    """Wrong password → 401 INVALID_CREDENTIALS. No domain hint."""
    mock_db.fetchrow.return_value = _make_pa_row()

    with patch("routers.auth_pa.verify_password", return_value=False):
        resp = await client.post("/auth/admin/login", json={
            "email": "admin@prana.in",
            "password": "WrongPass",
        })

    assert resp.status_code == 401
    assert "INVALID_CREDENTIALS" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_pa_login_non_prana_domain_returns_401(client, mock_db, mock_redis):
    """Non-@prana.in email is rejected before DB lookup."""
    resp = await client.post("/auth/admin/login", json={
        "email": "user@acme.com",
        "password": "AnyPass@123",
    })

    assert resp.status_code == 401
    # DB should NOT have been queried — domain check is pre-DB
    mock_db.fetchrow.assert_not_called()


# -- TOTP lockout (lock threshold = 3) ------------------------------------

@pytest.mark.asyncio
async def test_pa_totp_invalid_lockout(client, mock_db, mock_redis):
    """Third wrong TOTP locks the PA account (threshold=3, stricter than OA's 5)."""
    mock_redis.get = AsyncMock(return_value=b"pa-uuid-001")
    mock_redis.delete = AsyncMock()

    # failed_totp_count=2 already — one more triggers lockout
    # Two fetchrow calls: (1) PA row for TOTP, (2) platform_config for threshold
    mock_db.fetchrow.side_effect = [
        {
            "totp_secret_enc": b"\x00" * 32,
            "failed_totp_count": 2,
            "status": "ACTIVE",
        },
        {"config_value": "3"},
    ]

    with patch("routers.auth_pa.TOTPService") as MockTOTP:
        instance = MagicMock()
        instance.verify = MagicMock(return_value=False)
        MockTOTP.return_value = instance

        resp = await client.post("/auth/admin/totp", json={
            "step_token": "valid-step-token",
            "code": "999999",
        })

    assert resp.status_code == 403
    assert "ACCOUNT_LOCKED" in resp.json().get("detail", "")

    # DB must have been updated to LOCKED status
    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).upper()
    assert "LOCKED" in all_sql
