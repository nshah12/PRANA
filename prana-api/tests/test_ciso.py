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
from unittest.mock import AsyncMock, MagicMock

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
