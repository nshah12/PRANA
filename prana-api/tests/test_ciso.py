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
