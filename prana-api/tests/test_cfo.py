"""
Tests for routers/cfo.py - CFO financial analytics dashboard.

Covers:
  - Auth guard: requires cfo or oa_admin role
  - Privacy contract: no raw salary figures in any response
  - Tenant isolation: cannot access another tenant's data
  - Cohort minimum: payroll endpoint blocked if < 30 employees
  - Dashboard KPIs shape
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "cfo", tenant_id: str = "tenant-001",
              user_id: str = "cfo-uuid-001") -> None:
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
        "sub": "any", "user_type": "oa_user", "role": "cfo",
        "tenant_id": "tenant-001", "jti": "revoked-session",
    })
    jwt.is_revoked = AsyncMock(return_value=True)


# -- Auth guard ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_dashboard_requires_auth(client, mock_db):
    """Unauthenticated request must be rejected."""
    resp = await client.get("/v1/cfo/dashboard")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cfo_dashboard_requires_cfo_role(client, mock_db):
    """OA-Operator cannot access CFO endpoints."""
    _set_auth(client, role="oa_operator")
    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cfo_dashboard_rejects_ciso_role(client, mock_db):
    """CISO cannot access CFO endpoints."""
    _set_auth(client, role="ciso")
    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cfo_oa_admin_can_access(client, mock_db):
    """oa_admin must be able to access CFO endpoints (superrole)."""
    _set_auth(client, role="oa_admin")
    mock_db.fetchval.return_value = 50
    mock_db.fetchrow.return_value = {"granted": 40, "total": 50}

    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cfo_revoked_session_rejected(client, mock_db):
    _revoke_all(client)
    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# -- Dashboard KPIs ------------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_dashboard_happy_path_shape(client, mock_db):
    """Dashboard must return required KPI keys."""
    _set_auth(client)
    mock_db.fetchval.return_value = 100
    mock_db.fetchrow.return_value = {"granted": 85, "total": 100}

    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    for key in ("payroll_spend_label", "consent_coverage_pct", "active_anomalies"):
        assert key in data, f"Missing dashboard key: {key}"


# -- Privacy contract ----------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_response_contains_no_raw_salary_figures(client, mock_db):
    """CFO dashboard must never expose raw salary amounts."""
    _set_auth(client)
    mock_db.fetchval.return_value = 100
    mock_db.fetchrow.return_value = {"granted": 80, "total": 100}

    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.text.lower()
    for field in ("gross_salary", "net_salary", "basic_salary"):
        assert field not in body, f"Raw salary field '{field}' leaked in CFO response"


@pytest.mark.asyncio
async def test_cfo_payroll_no_individual_salaries(client, mock_db):
    """Payroll intelligence must return aggregated labels, never individual salary figures."""
    _set_auth(client)
    mock_db.fetchval.return_value = 50
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/cfo/payroll", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.text.lower()
    for raw_field in ("gross_salary", "net_salary", "basic_salary"):
        assert raw_field not in body, f"Individual salary '{raw_field}' leaked in payroll response"


# -- Cohort minimum ------------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_payroll_blocked_below_cohort_minimum(client, mock_db):
    """Payroll data must be blocked when active employee count < 30 (privacy floor)."""
    _set_auth(client)
    mock_db.fetchval.return_value = 15

    resp = await client.get("/v1/cfo/payroll", headers=AUTH_HEADER)

    assert resp.status_code == 403
    assert "COHORT_TOO_SMALL" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_cfo_payroll_available_above_cohort_minimum(client, mock_db):
    """Payroll data must be available when count >= 30."""
    _set_auth(client)
    mock_db.fetchval.return_value = 30
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/cfo/payroll", headers=AUTH_HEADER)

    assert resp.status_code == 200


# -- Tenant isolation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_tenant_isolation_blocks_cross_tenant(client, mock_db):
    """CFO only sees their own tenant's data - all DB queries must be tenant-scoped."""
    _set_auth(client, tenant_id="tenant-001")
    mock_db.fetchval.return_value = 50
    mock_db.fetchrow.return_value = {"granted": 40, "total": 50}

    resp = await client.get("/v1/cfo/dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    for call in mock_db.fetchval.call_args_list + mock_db.fetchrow.call_args_list:
        args = call[0]
        assert "tenant-001" in args, f"DB call missing tenant scope: {call}"


# -- Anomaly acknowledgement ---------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_anomaly_acknowledge_happy_path(client, mock_db):
    """CFO can acknowledge an anomaly - returns 200."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {
        "anomaly_id": "anom-uuid-001",
        "tenant_id": "tenant-001",
        "status": "OPEN",
    }

    resp = await client.post(
        "/v1/cfo/anomalies/anom-uuid-001/acknowledge",
        headers=AUTH_HEADER,
        json={"note": "Reviewed - expected due to bonus payout"},
    )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cfo_anomaly_acknowledge_missing_returns_404(client, mock_db):
    """Acknowledging a non-existent anomaly must return 404."""
    _set_auth(client)
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/cfo/anomalies/does-not-exist/acknowledge",
        headers=AUTH_HEADER,
        json={"note": "test"},
    )

    assert resp.status_code == 404
