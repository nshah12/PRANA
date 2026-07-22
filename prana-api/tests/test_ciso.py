"""
Tests for routers/ciso.py — CISO security dashboard.

Covers:
  - Auth guard: requires ciso or oa_admin role
  - Tenant isolation: cannot see another tenant's data
  - IP visibility: CISO sees full ip_address (not masked)
  - Flag suspicious access: PATCH /access-flags/{id}
  - No raw salary or PAN in any CISO response
"""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "ciso", tenant_id: str = "tenant-001",
              user_id: str = "ciso-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _revoke_all(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "any", "user_type": "oa_user", "role": "ciso",
        "tenant_id": "tenant-001", "jti": "revoked-session",
    })
    jwt.is_revoked = AsyncMock(return_value=True)


def _make_access_flag_row():
    return {
        "access_id":        "acc-uuid-001",
        "document_id":      "doc-uuid-001",
        "employee_user_id": "emp-uuid-001",
        "actor_type":       "EMPLOYEE",
        "access_type":      "VIEW",
        "access_channel":   "MOBILE",
        "ip_address":       "203.0.113.42",
        "accessed_at":      datetime.datetime(2024, 3, 1, 10, 0, 0),
        "flag_reason":      "Unusual access pattern",
        "is_flagged":       True,
        "doc_type":         "SALARY_SLIP",
        "doc_period":       "2024-03",
    }


# -- Auth guard ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_ciso_dashboard_requires_auth(client, mock_db):
    """Unauthenticated request must be rejected."""
    resp = await client.get("/v1/ciso/overview")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ciso_dashboard_requires_ciso_role(client, mock_db):
    """OA-Operator cannot access CISO endpoints."""
    _set_auth(client, role="oa_operator")
    resp = await client.get("/v1/ciso/overview", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ciso_dashboard_rejects_chro_role(client, mock_db):
    """CHRO cannot access CISO endpoints."""
    _set_auth(client, role="chro")
    resp = await client.get("/v1/ciso/overview", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ciso_oa_admin_can_access(client, mock_db):
    """oa_admin must be able to access CISO endpoints (superrole)."""
    _set_auth(client, role="oa_admin")
    mock_db.fetchval.return_value = 0
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/ciso/overview", headers=AUTH_HEADER)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ciso_revoked_session_rejected(client, mock_db):
    """Revoked JWT must be rejected."""
    _revoke_all(client)
    resp = await client.get("/v1/ciso/overview", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# -- IP visibility: CISO sees full IP -----------------------------------------

@pytest.mark.asyncio
async def test_ciso_access_log_shows_full_ip_to_ciso(client, mock_db):
    """CISO access-flags response must include the full ip_address field."""
    _set_auth(client)
    mock_db.fetch.return_value = [_make_access_flag_row()]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/v1/ciso/access-flags", headers=AUTH_HEADER)

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["ip_address"] == "203.0.113.42"


@pytest.mark.asyncio
async def test_ciso_access_flags_response_shape(client, mock_db):
    """Access-flags response must include required audit fields."""
    _set_auth(client)
    mock_db.fetch.return_value = [_make_access_flag_row()]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/v1/ciso/access-flags", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    item = data["items"][0]
    for field in ("access_id", "actor_type", "access_type", "ip_address",
                  "accessed_at", "flag_reason", "is_flagged"):
        assert field in item, f"Missing field: {field}"


# -- Flag suspicious access ----------------------------------------------------

@pytest.mark.asyncio
async def test_ciso_flag_suspicious_access(client, mock_db):
    """CISO can flag a document access log entry."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {"access_id": "acc-uuid-001"}

    resp = await client.patch(
        "/v1/ciso/access-flags/acc-uuid-001",
        headers=AUTH_HEADER,
        json={"is_flagged": True, "flag_reason": "Suspicious download at 2am"},
    )

    assert resp.status_code == 200
    mock_db.execute.assert_called_once()
    sql = str(mock_db.execute.call_args).lower()
    assert "is_flagged" in sql or "flag_reason" in sql


@pytest.mark.asyncio
async def test_ciso_flag_missing_record_returns_404(client, mock_db):
    """Flagging a non-existent access log must return 404."""
    _set_auth(client)
    mock_db.fetchrow.return_value = None

    resp = await client.patch(
        "/v1/ciso/access-flags/does-not-exist",
        headers=AUTH_HEADER,
        json={"is_flagged": True},
    )

    assert resp.status_code == 404


# -- employee_user.mobile column drift (schema.sql: no plaintext 'mobile' col) -

@pytest.mark.asyncio
async def test_share_analytics_shows_employee_full_name_via_employee_master(client, mock_db):
    """employee_user has no plaintext 'mobile' column at all (replaced by
    mobile_token + enc_mobile when mobile moved to encrypted-at-rest storage) —
    this query used to select eu.mobile directly, an UndefinedColumnError on
    every real call. The response field is literally named "employee_name", so
    the fix joins employee_master for the real name rather than decrypting a
    phone number into a name field."""
    _set_auth(client)
    mock_db.fetchval.return_value = 0
    mock_db.fetch.return_value = [{
        "token_id": "tok-1", "recipient_identifier": "friend@example.com",
        "expires_at": datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc),
        "usage_count": 2, "status": "ACTIVE", "emp_name": "Priya Sharma",
        "doc_type": "SALARY_SLIP",
    }]

    resp = await client.get("/v1/ciso/shares", headers=AUTH_HEADER)

    assert resp.status_code == 200
    query = mock_db.fetch.call_args.args[0]
    assert "employee_master" in query
    assert "eu.mobile" not in query
    body = resp.json()
    assert body["links"][0]["employee_name"] == "Priya Sharma"


@pytest.mark.asyncio
async def test_account_locks_decrypts_employee_mobile_via_kms(client, mock_db):
    """Same column-drift bug: the 'identifier' shown for a locked employee must
    come from enc_mobile decrypted via the platform auth CMK (same model as
    totp_secret_enc), not a nonexistent plaintext 'mobile' column."""
    _set_auth(client)
    client.app.state.kms_service.decrypt_value = MagicMock(return_value="+919000000001")
    mock_db.fetch.return_value = [{
        "event_id": "evt-1", "user_type": "employee", "user_id": "emp-1",
        "lock_reason": "POLICY_LOCK",
        "locked_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        "scheduled_unlock_at": None, "failed_attempt_count": 5, "last_failed_ip": None,
        "emp_enc_mobile": "kms-ciphertext-blob", "oa_email": None,
    }]

    resp = await client.get("/v1/ciso/account-locks", headers=AUTH_HEADER)

    assert resp.status_code == 200
    query = mock_db.fetch.call_args.args[0]
    assert "enc_mobile" in query
    assert "eu.mobile" not in query
    body = resp.json()
    assert body["items"][0]["identifier"] == "+919000000001"


@pytest.mark.asyncio
async def test_account_locks_oa_user_uses_email_not_mobile(client, mock_db):
    _set_auth(client)
    mock_db.fetch.return_value = [{
        "event_id": "evt-2", "user_type": "oa_user", "user_id": "oa-1",
        "lock_reason": "POLICY_LOCK",
        "locked_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        "scheduled_unlock_at": None, "failed_attempt_count": 3, "last_failed_ip": None,
        "emp_enc_mobile": None, "oa_email": "ops@acme.example",
    }]

    resp = await client.get("/v1/ciso/account-locks", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["identifier"] == "ops@acme.example"


# -- Tenant isolation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_ciso_tenant_isolation(client, mock_db):
    """CISO only sees data for their own tenant — not another tenant's flags."""
    _set_auth(client, tenant_id="tenant-001")
    mock_db.fetch.return_value = []
    mock_db.fetchval.return_value = 0

    resp = await client.get("/v1/ciso/access-flags", headers=AUTH_HEADER)

    assert resp.status_code == 200
    for call in mock_db.fetch.call_args_list + mock_db.fetchval.call_args_list:
        args = call[0]
        assert "tenant-001" in args, f"DB query missing tenant_id scope: {call}"


# -- Privacy contract ----------------------------------------------------------

@pytest.mark.asyncio
async def test_ciso_overview_no_raw_salary(client, mock_db):
    """CISO overview must never expose raw salary figures."""
    _set_auth(client)
    mock_db.fetchval.return_value = 0
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/ciso/overview", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body_str = resp.text.lower()
    for field in ("gross_salary", "net_salary", "basic_salary", "ctc"):
        assert field not in body_str, f"Salary field '{field}' leaked in CISO overview"


# -- Auth anomaly feed ---------------------------------------------------------

@pytest.mark.asyncio
async def test_ciso_auth_anomaly_feed_shape(client, mock_db):
    """Auth anomaly feed must include ip_address, anomaly_type, and detected_at."""
    _set_auth(client)
    mock_db.fetch.return_value = [{
        "event_id":      "log-uuid-001",
        "anomaly_type":  "FAILED",
        "ip_address":    "198.51.100.5",
        "ip_city":       "Mumbai",
        "ip_country":    "IN",
        "detected_at":   datetime.datetime(2024, 3, 1, 3, 0, 0),
        "session_id":    None,
        "is_foreign_ip": False,
        "severity":      "MEDIUM",
        "description":   "Multiple failed login attempts from this IP",
    }]

    resp = await client.get("/v1/ciso/auth-anomalies", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "anomalies" in data
    item = data["anomalies"][0]
    assert "ip_address" in item
    assert "anomaly_type" in item
    assert "detected_at" in item


# ── Digest endpoints ──────────────────────────────────────────────────────────

def _digest_db_setup(mock_db):
    mock_db.fetchval.side_effect = [1847, 3, 2, 1, 34]
    mock_db.fetch.side_effect = [
        [{"access_channel": "MOBILE", "cnt": 1256}],
        [],
    ]


@pytest.mark.asyncio
async def test_ciso_weekly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/ciso/digest/weekly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    d = resp.json()["digest"]
    assert "from" in d and "to" in d
    assert "period" not in d
    assert d["total_accesses"] == 1847
    assert d["anomalies_total"] == 3
    assert d["anomalies_open"] == 2
    assert d["force_logouts"] == 1
    assert d["share_tokens_period"] == 34
    assert isinstance(d["by_channel"], list)
    assert isinstance(d["incidents"], list)


@pytest.mark.asyncio
async def test_ciso_monthly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/ciso/digest/monthly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "from" in resp.json()["digest"]


@pytest.mark.asyncio
async def test_ciso_quarterly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/ciso/digest/quarterly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "from" in resp.json()["digest"]


@pytest.mark.asyncio
async def test_ciso_digest_rejects_range_over_184_days(client, mock_db):
    _set_auth(client)
    resp = await client.get(
        "/v1/ciso/digest/weekly?from=2025-01-01&to=2025-08-05",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "DATE_RANGE_TOO_LARGE"


@pytest.mark.asyncio
async def test_ciso_digest_privacy(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/ciso/digest/weekly", headers=AUTH_HEADER)
    import json as _j
    text = _j.dumps(resp.json()).lower()
    assert "pan" not in text
    assert "salary" not in text


@pytest.mark.asyncio
async def test_ciso_digest_settings_get(client, mock_db):
    _set_auth(client)
    import json as _json
    mock_db.fetchrow.return_value = {
        "config_value": _json.dumps({"recipients": [], "active": False,
                                      "schedules": {}, "sections": [], "format": "email"})
    }
    resp = await client.get("/v1/ciso/digest/settings", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "digest_settings" in resp.json()


@pytest.mark.asyncio
async def test_ciso_digest_settings_put(client, mock_db):
    _set_auth(client)
    mock_db.execute.return_value = None
    body = {"recipients": ["ciso@corp.in"], "schedules": {}, "sections": [], "format": "email", "active": True}
    resp = await client.put("/v1/ciso/digest/settings", headers=AUTH_HEADER, json=body)
    assert resp.status_code == 200
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_ciso_digest_requires_auth(client):
    from unittest.mock import MagicMock, AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={"sub": "x", "user_type": "oa_user", "role": "ciso",
                                          "tenant_id": "tenant-001", "jti": "s"})
    jwt.is_revoked = AsyncMock(return_value=True)
    resp = await client.get("/v1/ciso/digest/weekly", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# ── Incident endpoints ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ciso_incidents_list_requires_auth(client, mock_db):
    """Unauthenticated request to /incidents must be rejected."""
    resp = await client.get("/v1/ciso/incidents")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ciso_incidents_list_shape(client, mock_db):
    """GET /incidents returns items list scoped to tenant."""
    _set_auth(client)
    mock_db.fetch.return_value = [
        {
            "incident_id": "inc-uuid-001",
            "tenant_id": "tenant-001",
            "incident_type": "SECURITY_ANOMALY",
            "severity": "P1",
            "title": "Bulk access detected",
            "status": "OPEN",
            "sla_deadline": datetime.datetime(2026, 6, 19, 14, 0, 0, tzinfo=datetime.timezone.utc),
            "escalated_at": None,
            "resolved_at": None,
            "created_at": datetime.datetime(2026, 6, 19, 10, 0, 0, tzinfo=datetime.timezone.utc),
            "assigned_role": "CISO",
            "assigned_to": None,
        }
    ]
    resp = await client.get("/v1/ciso/incidents", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["items"][0]["severity"] == "P1"


@pytest.mark.asyncio
async def test_ciso_incidents_scoped_to_tenant(client, mock_db):
    """incident list DB call must include the CISO's tenant_id."""
    _set_auth(client, tenant_id="tenant-001")
    mock_db.fetch.return_value = []
    await client.get("/v1/ciso/incidents", headers=AUTH_HEADER)
    sql, *args = mock_db.fetch.call_args[0]
    assert "tenant-001" in args


@pytest.mark.asyncio
async def test_ciso_resolve_incident_happy_path(client, mock_db):
    """PATCH /incidents/{id}/resolve returns 200 on success."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {
        "incident_id": "inc-uuid-001",
        "tenant_id": "tenant-001",
        "status": "OPEN",
    }
    mock_db.execute.return_value = None
    resp = await client.patch(
        "/v1/ciso/incidents/inc-uuid-001/resolve",
        headers=AUTH_HEADER,
        json={"resolution_note": "False positive — confirmed bulk export job"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_ciso_resolve_incident_not_found(client, mock_db):
    """Resolving non-existent incident returns 404."""
    _set_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.patch(
        "/v1/ciso/incidents/does-not-exist/resolve",
        headers=AUTH_HEADER,
        json={"resolution_note": "test"},
    )
    assert resp.status_code == 404


# ── Application errors (4th incident track, ERROR_OBSERVABILITY_DESIGN.md §7) ───

ERR_SVC = "services.error_observability_service.ErrorObservabilityService"


@pytest.mark.asyncio
async def test_ciso_errors_list_requires_auth(client, mock_db):
    resp = await client.get("/v1/ciso/errors")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ciso_errors_list_is_tenant_scoped_including_platform_level(client, mock_db):
    """CISO must see their own tenant's errors AND platform-level (tenant_id IS NULL) ones,
    but never another tenant's — see ERROR_OBSERVABILITY_DESIGN.md §7."""
    _set_auth(client, tenant_id="tenant-001")
    with patch(f"{ERR_SVC}.list_errors", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"error_id": "e-1", "exception_type": "RuntimeError"}]
        resp = await client.get("/v1/ciso/errors", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    mock_list.assert_awaited_once()
    kwargs = mock_list.call_args.kwargs
    assert kwargs["tenant_id"] == "tenant-001"
    assert kwargs["include_platform_errors"] is True


@pytest.mark.asyncio
async def test_ciso_acknowledge_error(client, mock_db):
    _set_auth(client)
    with patch(f"{ERR_SVC}.acknowledge", new_callable=AsyncMock) as mock_ack:
        resp = await client.patch("/v1/ciso/errors/e-1/acknowledge", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"
    mock_ack.assert_awaited_once_with(error_id="e-1")


@pytest.mark.asyncio
async def test_ciso_resolve_error_happy_path(client, mock_db):
    _set_auth(client, user_id="ciso-uuid-009")
    with patch(f"{ERR_SVC}.resolve", new_callable=AsyncMock) as mock_resolve:
        resp = await client.patch(
            "/v1/ciso/errors/e-1/resolve", headers=AUTH_HEADER,
            json={"resolution_note": "Confirmed benign, deployed fix"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    mock_resolve.assert_awaited_once_with(
        error_id="e-1", resolved_by="ciso-uuid-009", resolution_note="Confirmed benign, deployed fix",
    )


@pytest.mark.asyncio
async def test_ciso_resolve_error_not_found(client, mock_db):
    _set_auth(client)
    with patch(f"{ERR_SVC}.resolve", new_callable=AsyncMock,
                side_effect=ValueError("error_event not found: e-missing")):
        resp = await client.patch(
            "/v1/ciso/errors/e-missing/resolve", headers=AUTH_HEADER,
            json={"resolution_note": "test"},
        )
    assert resp.status_code == 404


# ── Notification log endpoint ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ciso_notification_log_shape(client, mock_db):
    """GET /notification-log returns items scoped to tenant."""
    _set_auth(client)
    mock_db.fetch.return_value = [
        {
            "notification_id": "notif-uuid-001",
            "event_type": "ANOMALY_DETECTED",
            "channel": "EMAIL",
            "template_id": "ANOMALY_P1_ALERT",
            "status": "SENT",
            "sent_at": datetime.datetime(2026, 6, 19, 10, 0, 0, tzinfo=datetime.timezone.utc),
            "failed_at": None,
            "error_message": None,
            "created_at": datetime.datetime(2026, 6, 19, 10, 0, 0, tzinfo=datetime.timezone.utc),
        }
    ]
    resp = await client.get("/v1/ciso/notification-log", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["items"][0]["channel"] == "EMAIL"


# ── Account lock management — schema.sql uses user_type/user_id, not ------
# ── account_type/account_id (which don't exist on account_status_event) ---

@pytest.mark.asyncio
async def test_list_account_locks_queries_real_columns(client, mock_db):
    """GET /account-locks must query user_type/user_id (the real
    account_status_event columns per schema.sql:374-397) — not
    account_type/account_id, which don't exist and would 500 in production.
    """
    _set_auth(client)
    client.app.state.kms_service.decrypt_value = MagicMock(return_value="+919000000001")
    mock_db.fetch.return_value = [{
        "event_id": "event-uuid-001", "user_type": "employee", "user_id": "emp-uuid-001",
        "lock_reason": "POLICY_LOCK", "locked_at": datetime.datetime(2026, 6, 19, tzinfo=datetime.timezone.utc),
        "scheduled_unlock_at": None, "failed_attempt_count": 5, "last_failed_ip": None,
        "emp_enc_mobile": "kms-ciphertext-blob", "oa_email": None,
    }]

    resp = await client.get("/v1/ciso/account-locks", headers=AUTH_HEADER)

    assert resp.status_code == 200
    sql = mock_db.fetch.call_args.args[0].lower()
    assert "ase.account_type" not in sql
    assert "ase.account_id" not in sql
    assert "ase.user_type" in sql
    assert "ase.user_id" in sql
    assert resp.json()["items"][0]["account_type"] == "employee"


# ── Manual account unlock ────────────────────────────────────────────────────
# Regression: manual_unlock previously read lock_row["account_type"]/["account_id"],
# but the SELECT only fetches user_type/user_id — a real DB row raises KeyError
# on every call. Zero test coverage previously existed to catch this.

@pytest.mark.asyncio
async def test_manual_unlock_requires_auth(client, mock_db):
    resp = await client.post("/v1/ciso/account-locks/evt-1/unlock")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_manual_unlock_not_found_returns_404(client, mock_db):
    _set_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post("/v1/ciso/account-locks/evt-missing/unlock", headers=AUTH_HEADER)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_unlock_already_unlocked_returns_409(client, mock_db):
    _set_auth(client)
    mock_db.fetchrow.return_value = {
        "event_id": "evt-1", "user_type": "employee", "user_id": "emp-uuid-001",
        "reversed_by_event_id": "evt-0",
    }
    resp = await client.post("/v1/ciso/account-locks/evt-1/unlock", headers=AUTH_HEADER)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_manual_unlock_restores_employee_account(client, mock_db, mock_kafka):
    _set_auth(client, tenant_id="tenant-001", user_id="ciso-uuid-001")
    mock_db.fetchrow.return_value = {
        "event_id": "evt-1", "user_type": "employee", "user_id": "emp-uuid-001",
        "reversed_by_event_id": None,
    }
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/v1/ciso/account-locks/evt-1/unlock", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["message"] == "LOCK_REMOVED"
    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "employee_user" in all_sql and "emp-uuid-001" in all_sql
    mock_kafka.security_event.assert_awaited_once()
    sec = mock_kafka.security_event.call_args[0][0]
    assert sec["event_type"] == "ACCOUNT_UNLOCKED"
    assert sec["target_account_id"] == "emp-uuid-001"


@pytest.mark.asyncio
async def test_manual_unlock_restores_oa_user_account(client, mock_db, mock_kafka):
    _set_auth(client, tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {
        "event_id": "evt-2", "user_type": "oa_user", "user_id": "oa-uuid-002",
        "reversed_by_event_id": None,
    }
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/v1/ciso/account-locks/evt-2/unlock", headers=AUTH_HEADER)

    assert resp.status_code == 200
    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "oa_user" in all_sql and "oa-uuid-002" in all_sql


# ── OA Activity Audit — Portal Admin visibility ─────────────────────────────────
# PA-initiated employee TOTP resets must be visible to the tenant CISO, not just
# OA-Operator/OA-Admin actions — closes the gap where actor_type='PORTAL_ADMIN'
# rows were silently excluded from this endpoint.

def _make_totp_reset_audit_row(actor_type: str = "PORTAL_ADMIN"):
    return {
        "event_id":      "evt-uuid-001",
        "action_type":   "EMPLOYEE_TOTP_RESET",
        "actor_id":      "pa-uuid-777",
        "actor_type":    actor_type,
        "resource_id":   "emp-uuid-001",
        "ip_address":    "203.0.113.10",
        "created_at":    datetime.datetime(2026, 7, 10, 9, 0, 0, tzinfo=datetime.timezone.utc),
        "actor_name":    "pa-admin@prana.in",
        "actor_role":    "portal_admin",
        "reason":        "Support escalation TCK-1234",
    }


@pytest.mark.asyncio
async def test_oa_audit_includes_portal_admin_actor_type(client, mock_db):
    """A PA-initiated event (e.g. EMPLOYEE_TOTP_RESET override) must appear in the
    tenant's OA activity audit feed — not be filtered out for having actor_type
    PORTAL_ADMIN instead of an OA_* value."""
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetch.return_value = [_make_totp_reset_audit_row()]

    resp = await client.get("/v1/ciso/oa-audit", headers=AUTH_HEADER)

    assert resp.status_code == 200
    where_clause = mock_db.fetch.call_args[0][0]
    assert "PORTAL_ADMIN" in where_clause
    events = resp.json()["events"]
    assert events[0]["actor_type"] == "PORTAL_ADMIN"


@pytest.mark.asyncio
async def test_oa_audit_still_scoped_to_tenant_for_portal_admin_events(client, mock_db):
    """Even a platform-wide PA action must appear only under the specific tenant_id
    the AuditConsumer recorded it under (the affected employee's own tenant)."""
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/ciso/oa-audit", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "tenant-001" in mock_db.fetch.call_args[0]


@pytest.mark.asyncio
async def test_oa_audit_exposes_affected_employee_as_resource_id(client, mock_db):
    """Non-document events (like a TOTP reset) have no document_id — the affected
    employee_uuid from event_metadata must be surfaced as resource_id instead."""
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetch.return_value = [_make_totp_reset_audit_row()]

    resp = await client.get("/v1/ciso/oa-audit", headers=AUTH_HEADER)

    assert resp.status_code == 200
    events = resp.json()["events"]
    assert events[0]["resource_id"] == "emp-uuid-001"


@pytest.mark.asyncio
async def test_oa_audit_export_includes_portal_admin_actor_type(client, mock_db):
    """CSV export must not silently drop PA-initiated events either."""
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetch.return_value = [{
        "event_type":   "EMPLOYEE_TOTP_RESET",
        "actor_id":     "pa-uuid-777",
        "actor_type":   "PORTAL_ADMIN",
        "actor_name":   "pa-admin@prana.in",
        "actor_role":   "portal_admin",
        "document_id":  None,
        "resource_id":  "emp-uuid-001",
        "ip_address":   "203.0.113.10",
        "occurred_at":  datetime.datetime(2026, 7, 10, 9, 0, 0, tzinfo=datetime.timezone.utc),
    }]

    resp = await client.get("/v1/ciso/oa-audit/export", headers=AUTH_HEADER)

    assert resp.status_code == 200
    where_clause = mock_db.fetch.call_args[0][0]
    assert "PORTAL_ADMIN" in where_clause
