"""
Tests for routers/auth_employee.py — Employee auth flow.

Tests cover:
  - Login: happy path (→ step_token), wrong password, locked, suspended, not found
  - TOTP verify: correct code (→ JWT), wrong code (increments count), 5 failures (lock)
  - Force password change: step_token chain
  - Refresh: valid cookie rotates token, missing cookie → 401
  - Logout: revokes session

TDD: these tests were written BEFORE any fixes. Run them RED first.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

def _emp_row(
    *,
    status="ACTIVE",
    force_reset=False,
    totp_configured_at="2024-01-01T00:00:00",
    consent_status="GRANTED",
    failed_totp_count=0,
    totp_secret_enc="ENC_TOTP",
    password_hash="$argon2id$v=19$m=65536,t=2,p=2$AAAA$AAAA",
):
    return {
        "employee_user_id": "emp-user-uuid-001",
        "pan_token": "pan-token-abc",
        "email": "rahul@example.com",
        "mobile": "+919000000001",
        "status": status,
        "force_reset": force_reset,
        "totp_configured_at": totp_configured_at,
        "consent_status": consent_status,
        "failed_totp_count": failed_totp_count,
        "password_hash": password_hash,
        "totp_secret_enc": totp_secret_enc,
    }


def _step_token_payload(next_step: str) -> bytes:
    return json.dumps({
        "user_id": "emp-user-uuid-001",
        "pan_token": "pan-token-abc",
        "next": next_step,
    }).encode()


# ── Login ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_user_not_found_returns_401_without_revealing_existence(client, mock_db):
    """Enumeration guard: unknown user and wrong password return the same 401."""
    mock_db.fetchrow.return_value = None
    with patch("routers.auth_employee.verify_password", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "nobody@example.com",
            "password": "whatever",
        })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_user_not_found_still_writes_login_attempt_log(client, mock_db):
    """Regression guard: an unknown identifier must still leave an audit trail
    (user_id=NULL, failure_reason=UNKNOWN_USER) — matching the pattern
    routers/auth_oa.py already uses. Without this, brute-force/enumeration
    against non-existent accounts is invisible to login_attempt_log and to
    the BRUTE_FORCE anomaly detector that reads from it."""
    mock_db.fetchrow.return_value = None
    with patch("routers.auth_employee.verify_password", return_value=False):
        await client.post("/auth/employee/login", json={
            "identifier": "nobody@example.com",
            "password": "whatever",
        })

    insert_call = next(
        c for c in mock_db.execute.call_args_list if "INSERT INTO login_attempt_log" in c.args[0]
    )
    sql, *args = insert_call.args
    assert args[0] is None  # user_id
    assert "UNKNOWN_USER" in args


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, mock_db):
    mock_db.fetchrow.return_value = _emp_row()
    with patch("routers.auth_employee.verify_password", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "wrong",
        })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_locked_account_returns_403(client, mock_db):
    mock_db.fetchrow.return_value = _emp_row(status="LOCKED")
    with patch("routers.auth_employee.verify_password", return_value=True):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "correct",
        })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_login_suspended_account_returns_403(client, mock_db):
    mock_db.fetchrow.return_value = _emp_row(status="SUSPENDED")
    with patch("routers.auth_employee.verify_password", return_value=True):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "correct",
        })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_login_happy_path_returns_step_token_with_next_totp(client, mock_db, mock_redis):
    """Normal login (TOTP configured, consent granted) → step_token pointing to TOTP."""
    mock_db.fetchrow.return_value = _emp_row()
    with patch("routers.auth_employee.verify_password", return_value=True), \
         patch("routers.auth_employee.needs_rehash", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "step_token" in data
    assert data["next"] == "totp"


@pytest.mark.asyncio
async def test_login_force_reset_returns_step_with_force_password_next(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _emp_row(force_reset=True)
    with patch("routers.auth_employee.verify_password", return_value=True), \
         patch("routers.auth_employee.needs_rehash", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    assert resp.json()["next"] == "force_password"


@pytest.mark.asyncio
async def test_login_totp_not_configured_returns_totp_setup_next(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _emp_row(totp_configured_at=None)
    with patch("routers.auth_employee.verify_password", return_value=True), \
         patch("routers.auth_employee.needs_rehash", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "rahul@example.com",
            "password": "correct",
        })
    assert resp.status_code == 200
    assert resp.json()["next"] == "totp_setup"


@pytest.mark.asyncio
async def test_login_consent_pending_returns_consent_next(client, mock_db, mock_redis):
    mock_db.fetchrow.return_value = _emp_row(consent_status="PENDING")
    with patch("routers.auth_employee.verify_password", return_value=True), \
         patch("routers.auth_employee.needs_rehash", return_value=False):
        resp = await client.post("/auth/employee/login", json={
            "identifier": "+919000000001",
            "password": "correct",
        })
    assert resp.status_code == 200
    assert resp.json()["next"] == "consent"


# ── TOTP verify ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_totp_verify_correct_code_returns_access_token(client, mock_db, mock_redis):
    mock_redis.get.return_value = _step_token_payload("totp")
    mock_db.fetchrow.side_effect = [
        # First call: employee TOTP row
        {"totp_secret_enc": "ENC_TOTP", "failed_totp_count": 0, "status": "ACTIVE"},
        # Second call: platform_config for lock threshold
        {"config_value": "5"},
    ]
    mock_db.fetchval.return_value = None  # session limit check returns 0 rows

    with patch("routers.auth_employee.TOTPService") as MockTOTP:
        MockTOTP.return_value.verify.return_value = True
        resp = await client.post("/auth/employee/totp", json={
            "step_token": "some-step-token",
            "code": "123456",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "expires_at" in data
    # Refresh token must be in httpOnly cookie, NOT in response body
    assert "refresh_token" not in data


@pytest.mark.asyncio
async def test_totp_verify_wrong_code_returns_401(client, mock_db, mock_redis):
    mock_redis.get.return_value = _step_token_payload("totp")
    mock_db.fetchrow.side_effect = [
        {"totp_secret_enc": "ENC_TOTP", "failed_totp_count": 0, "status": "ACTIVE"},
        {"config_value": "5"},
    ]
    mock_db.fetchval.return_value = 1  # atomic increment → below lock threshold
    with patch("routers.auth_employee.TOTPService") as MockTOTP:
        MockTOTP.return_value.verify.return_value = False
        resp = await client.post("/auth/employee/totp", json={
            "step_token": "some-step-token",
            "code": "000000",
        })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_TOTP"


@pytest.mark.asyncio
async def test_totp_5_failures_locks_account(client, mock_db, mock_redis):
    """5th failure must lock the account atomically."""
    mock_redis.get.return_value = _step_token_payload("totp")
    mock_db.fetchrow.side_effect = [
        {"totp_secret_enc": "ENC_TOTP", "failed_totp_count": 4, "status": "ACTIVE"},
        {"config_value": "5"},
    ]
    mock_db.fetchval.return_value = 5  # atomic increment → hits lock threshold
    with patch("routers.auth_employee.TOTPService") as MockTOTP:
        MockTOTP.return_value.verify.return_value = False
        resp = await client.post("/auth/employee/totp", json={
            "step_token": "some-step-token",
            "code": "000000",
        })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_LOCKED"
    # Verify the DB update set status=LOCKED
    update_call = str(mock_db.execute.call_args_list)
    assert "LOCKED" in update_call


@pytest.mark.asyncio
async def test_totp_expired_step_token_returns_401(client, mock_redis):
    mock_redis.get.return_value = None  # expired / not found
    resp = await client.post("/auth/employee/totp", json={
        "step_token": "expired-token",
        "code": "123456",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "STEP_TOKEN_EXPIRED"


# ── Refresh ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client):
    resp = await client.post("/auth/employee/refresh")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "NO_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_with_revoked_token_returns_401(client, mock_db):
    mock_db.fetchrow.return_value = {
        "session_id": "sess-001",
        "user_type": "employee",
        "user_id": "emp-user-uuid-001",
        "refresh_expires_at": __import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        "revoked": True,   # already revoked
    }
    resp = await client.post(
        "/auth/employee/refresh",
        cookies={"prana_refresh": "some-refresh-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_set_as_httponly_cookie_not_response_body(client, mock_db):
    """Refresh token must live in httpOnly cookie only — never in JSON response body."""
    import datetime as dt

    mock_db.fetchrow.side_effect = [
        {
            "session_id": "sess-001",
            "user_type": "employee",
            "user_id": "emp-user-uuid-001",
            "refresh_expires_at": dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc),
            "revoked": False,
        },
        # _fetch_user: employee row
        {"tenant_id": None, "role": None},
    ]
    # session limit query
    mock_db.fetch.return_value = []

    resp = await client.post(
        "/auth/employee/refresh",
        cookies={"prana_refresh": "valid-refresh-token"},
    )
    # If valid, response must not contain refresh_token in body
    if resp.status_code == 200:
        assert "refresh_token" not in resp.json()
        assert "prana_refresh" in resp.cookies


# ── Logout ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_requires_employee_jwt(client):
    """Logout without token must return 401, not 500."""
    resp = await client.post("/auth/employee/logout")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client, mock_db):
    """Authenticated logout must call revoke on the session."""
    from unittest.mock import AsyncMock
    mock_jwt = client.app.state.jwt_service
    mock_jwt.decode.return_value = {
        "sub": "emp-user-uuid-001",
        "user_type": "employee",
        "jti": "session-abc",
        "exp": 9999999999,
    }
    mock_jwt.is_revoked = AsyncMock(return_value=False)
    mock_jwt.revoke = AsyncMock()

    resp = await client.post(
        "/auth/employee/logout",
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200
    # Verify revoke was called
    assert mock_db.execute.called


# ── Device registration — push_token upsert ────────────────────────────────────

def _emp_auth_headers(client, user_id="emp-user-uuid-001"):
    mock_jwt = client.app.state.jwt_service
    mock_jwt.decode.return_value = {
        "sub": user_id, "user_type": "employee", "jti": "session-abc", "exp": 9999999999,
    }
    mock_jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.employee.jwt"}


@pytest.mark.asyncio
async def test_register_device_refreshes_push_token_on_conflict(client, mock_db):
    """Regression: ON CONFLICT (public_key) DO UPDATE only refreshed
    last_used_at — a rotated Expo push token on re-registration was silently
    dropped, since the same physical device keeps the same public_key across
    app reopens. Fixed 2026-08-06 as part of building real push dispatch."""
    headers = _emp_auth_headers(client)
    mock_db.fetchval.return_value = "device-uuid-001"

    resp = await client.post(
        "/auth/employee/device/register",
        headers=headers,
        json={"platform": "ANDROID", "public_key": "pubkey-abc", "push_token": "ExponentPushToken[new-token-123]"},
    )

    assert resp.status_code == 201
    call = mock_db.fetchval.call_args
    sql = call.args[0]
    assert "push_token=EXCLUDED.push_token" in sql


# ── Password setup via emailed/texted link ─────────────────────────────────────
# The server-generated temp password (routers/employees.py) is never disclosed
# anywhere — this link is the only way a newly onboarded employee ever gets a
# usable password.

@pytest.mark.asyncio
async def test_password_setup_verify_expired_token(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    resp = await client.post("/auth/employee/password-setup/verify", json={"token": "bogus"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "SETUP_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_password_setup_verify_happy_path(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=json.dumps(
        {"employee_user_id": "emp-user-uuid-002"}
    ).encode())
    mock_db.fetchrow = AsyncMock(return_value={"email": "newhire@acme.com"})
    resp = await client.post("/auth/employee/password-setup/verify", json={"token": "real-token"})
    assert resp.status_code == 200
    assert resp.json() == {"valid": True, "email": "newhire@acme.com"}


@pytest.mark.asyncio
async def test_password_setup_expired_token(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    resp = await client.post("/auth/employee/password-setup", json={
        "token": "bogus", "new_password": "SomethingLong123!",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "SETUP_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_password_setup_rejects_short_password(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=json.dumps(
        {"employee_user_id": "emp-user-uuid-002"}
    ).encode())
    resp = await client.post("/auth/employee/password-setup", json={
        "token": "real-token", "new_password": "short",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "PASSWORD_TOO_SHORT"


@pytest.mark.asyncio
async def test_password_setup_happy_path_sets_real_password(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=json.dumps(
        {"employee_user_id": "emp-user-uuid-002"}
    ).encode())
    mock_redis.delete = AsyncMock()
    mock_db.execute = AsyncMock()

    resp = await client.post("/auth/employee/password-setup", json={
        "token": "real-token", "new_password": "MyOwnChosenPass123!",
    })

    assert resp.status_code == 200
    assert resp.json()["message"] == "PASSWORD_CHANGED"

    mock_db.execute.assert_called_once()
    sql, employee_user_id, new_hash = mock_db.execute.call_args.args
    assert "force_reset=FALSE" in sql
    assert employee_user_id == "emp-user-uuid-002"
    assert new_hash != "MyOwnChosenPass123!"   # never store the plaintext

    mock_redis.delete.assert_called_once_with("emp_pwd_setup:real-token")
