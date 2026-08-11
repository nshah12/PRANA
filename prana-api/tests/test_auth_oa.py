"""
Tests for OA (Org Admin) authentication flow.

Covers:
  - Login: happy path, wrong password, account locked, account not found
  - TOTP: happy path, invalid code, lockout at 5 failures
  - Step-token chain: login → totp
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── H1: rate limiting ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_rate_limited_after_threshold(client, mock_db, mock_redis):
    """After the 10/min cap, further OA login attempts from the same IP get 429."""
    mock_db.fetchrow = AsyncMock(return_value=None)  # unknown user → 401 each attempt
    mock_db.execute = AsyncMock()
    statuses = []
    for _ in range(12):
        r = await client.post("/auth/org/login", json={"email": "spray@acme.in", "password": "x"})
        statuses.append(r.status_code)
    assert 429 in statuses, f"expected a 429 after the rate limit, got {statuses}"


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
    mock_db.fetchval = AsyncMock(return_value=5)  # atomic increment returns 5 → lock

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
    mock_db.fetchval = AsyncMock(return_value=2)  # atomic increment returns 2 → below lock

    with patch("routers.auth_oa.TOTPService.verify", return_value=False):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy-step-token",
            "code": "999999",
        })

    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_TOTP"


@pytest.mark.asyncio
async def test_totp_lockout_publishes_auth_event_for_async_escalation(client, mock_db, mock_redis, mock_kafka):
    """The synchronous status='LOCKED' write blocks the next login attempt immediately,
    but CISO/PA dashboard visibility and eventual unlock come from AuthConsumer's async
    escalation (PolicyLockWorkflow), which only fires off a published auth_event — same
    mechanism routers/auth_employee.py already used. Before this fix, OA account lockouts
    published nothing, so they never reached account_status_event or any CISO dashboard.
    """
    step_payload = b"oa-user-uuid-001:tenant-uuid-001:oa_admin"
    mock_redis.get = AsyncMock(return_value=step_payload)
    mock_redis.delete = AsyncMock()

    def _fetchrow_side(*args, **kwargs):
        sql = args[0].lower() if args else ""
        if "platform_config" in sql:
            return None
        return _make_oa_row(failed_totp_count=4)

    mock_db.fetchrow = AsyncMock(side_effect=_fetchrow_side)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value=5)

    with patch("routers.auth_oa.TOTPService.verify", return_value=False):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy-step-token",
            "code": "000000",
        })

    assert resp.status_code == 403
    mock_kafka.auth_event.assert_awaited_once()
    event = mock_kafka.auth_event.await_args.args[0]
    assert event["event_type"] == "TOTP_FAILED"
    assert event["user_id"] == "oa-user-uuid-001"
    assert event["user_type"] == "oa_user"
    assert event["locked"] is True
    assert event["fail_count"] == 5


@pytest.mark.asyncio
async def test_totp_failure_below_lockout_still_publishes_auth_event(client, mock_db, mock_redis, mock_kafka):
    """Every failure feeds AuthConsumer's rolling-window count, not just the one that
    crosses the lock threshold — AuthConsumer recomputes the count itself from
    login_attempt_log, so it just needs to be woken up on each failure.
    """
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
    mock_db.fetchval = AsyncMock(return_value=2)

    with patch("routers.auth_oa.TOTPService.verify", return_value=False):
        resp = await client.post("/auth/org/totp", json={
            "step_token": "dummy-step-token",
            "code": "999999",
        })

    assert resp.status_code == 401
    mock_kafka.auth_event.assert_awaited_once()
    event = mock_kafka.auth_event.await_args.args[0]
    assert event["event_type"] == "TOTP_FAILED"
    assert event["locked"] is False
    assert event["fail_count"] == 2


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


# ── Password setup via emailed link (new OA users have no other way to log in) ─

@pytest.mark.asyncio
async def test_password_setup_verify_expired_token(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    resp = await client.post("/auth/org/password-setup/verify", json={"token": "bogus"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "SETUP_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_password_setup_verify_happy_path(client, mock_db, mock_redis):
    import json as _json
    mock_redis.get = AsyncMock(return_value=_json.dumps(
        {"oa_user_id": "oa-user-uuid-002", "tenant_id": "tenant-uuid-001", "role": "chro"}
    ).encode())
    mock_db.fetchrow = AsyncMock(return_value={"email": "chro@acme.com"})
    resp = await client.post("/auth/org/password-setup/verify", json={"token": "real-token"})
    assert resp.status_code == 200
    assert resp.json() == {"valid": True, "email": "chro@acme.com"}


@pytest.mark.asyncio
async def test_password_setup_expired_token(client, mock_db, mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    resp = await client.post("/auth/org/password-setup", json={
        "token": "bogus", "new_password": "SomethingLong123!",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "SETUP_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_password_setup_rejects_short_password(client, mock_db, mock_redis):
    import json as _json
    mock_redis.get = AsyncMock(return_value=_json.dumps(
        {"oa_user_id": "oa-user-uuid-002", "tenant_id": "tenant-uuid-001", "role": "chro"}
    ).encode())
    resp = await client.post("/auth/org/password-setup", json={
        "token": "real-token", "new_password": "short",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "PASSWORD_TOO_SHORT"


@pytest.mark.asyncio
async def test_password_setup_happy_path_sets_real_password_and_clears_force_reset(client, mock_db, mock_redis):
    """This is the only path that gets oa_operator/chro/cfo/ciso a usable password —
    POST /v1/org/users never discloses the server-generated temp password anywhere."""
    import json as _json
    mock_redis.get = AsyncMock(return_value=_json.dumps(
        {"oa_user_id": "oa-user-uuid-002", "tenant_id": "tenant-uuid-001", "role": "chro"}
    ).encode())
    mock_redis.delete = AsyncMock()
    mock_db.execute = AsyncMock()

    resp = await client.post("/auth/org/password-setup", json={
        "token": "real-token", "new_password": "MyOwnChosenPass123!",
    })

    assert resp.status_code == 200
    assert resp.json()["message"] == "PASSWORD_CHANGED"

    mock_db.execute.assert_called_once()
    sql, oa_user_id, new_hash = mock_db.execute.call_args.args
    assert "force_reset=FALSE" in sql
    assert "temp_password_hash=NULL" in sql
    assert oa_user_id == "oa-user-uuid-002"
    assert new_hash != "MyOwnChosenPass123!"   # never store the plaintext

    # Single-use: token consumed on success
    mock_redis.delete.assert_called_once_with("oa_pwd_setup:real-token")
