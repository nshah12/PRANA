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


# -- Anomaly list --------------------------------------------------------------

@pytest.mark.asyncio
async def test_cfo_anomalies_list_shape(client, mock_db):
    """GET /anomalies returns anomalies keyed by rule_name (not anomaly_type)."""
    _set_auth(client)
    mock_db.fetch.return_value = [
        {
            "anomaly_id": "anom-uuid-001",
            "type": "BULK_ACCESS",        # asyncpg returns the column alias
            "financial_pattern": "high_volume",
            "detected_at": None,
            "severity": "P1",
            "status": "OPEN",
        }
    ]
    resp = await client.get("/v1/cfo/anomalies", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "anomalies" in data
    assert data["total"] == 1
    assert data["anomalies"][0]["type"] == "BULK_ACCESS"


@pytest.mark.asyncio
async def test_cfo_anomalies_requires_cfo_role(client, mock_db):
    _set_auth(client, role="oa_operator")
    resp = await client.get("/v1/cfo/anomalies", headers=AUTH_HEADER)
    assert resp.status_code == 403


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


# ── Digest endpoints ──────────────────────────────────────────────────────────

def _digest_db_setup(mock_db):
    """Configure mock_db with enough side_effects for CFO digest (all periods)."""
    import json as _json
    mock_db.fetchval.side_effect = [1997, 22, 11, 2]
    mock_db.fetchrow.side_effect = [
        {"config_value": "1500000"},
        {"config_value": "150000"},
        {"config_value": "2050"},
    ]
    mock_db.fetch.side_effect = [
        [{"doc_type": "SALARY_SLIP", "covered": 1960}],
        [{"department": "Engineering", "cnt": 800}],
    ]


@pytest.mark.asyncio
async def test_cfo_weekly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/cfo/digest/weekly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    d = resp.json()["digest"]
    assert "from" in d and "to" in d
    assert "period" not in d
    assert d["headcount"] == 1997
    assert d["exits"] == 22
    assert d["joiners"] == 11
    assert d["anomalies_pending"] == 2
    assert "cost_indicators" in d
    assert "note" in d["cost_indicators"]


@pytest.mark.asyncio
async def test_cfo_monthly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/cfo/digest/monthly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "from" in resp.json()["digest"]


@pytest.mark.asyncio
async def test_cfo_quarterly_digest_shape(client, mock_db):
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/cfo/digest/quarterly", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "from" in resp.json()["digest"]


@pytest.mark.asyncio
async def test_cfo_digest_rejects_range_over_184_days(client, mock_db):
    _set_auth(client)
    resp = await client.get(
        "/v1/cfo/digest/weekly?from=2025-01-01&to=2025-08-05",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "DATE_RANGE_TOO_LARGE"


@pytest.mark.asyncio
async def test_cfo_digest_privacy(client, mock_db):
    """cost_indicators must never leak raw salary — only CFO estimates."""
    _set_auth(client)
    _digest_db_setup(mock_db)
    resp = await client.get("/v1/cfo/digest/weekly", headers=AUTH_HEADER)
    import json as _j
    text = _j.dumps(resp.json()).lower()
    assert "pan" not in text
    assert "nik" not in text
    # cost_indicators.note must confirm these are estimates
    note = resp.json()["digest"]["cost_indicators"]["note"].lower()
    assert "estimate" in note


@pytest.mark.asyncio
async def test_cfo_digest_settings_get(client, mock_db):
    _set_auth(client)
    import json as _json
    mock_db.fetchrow.return_value = {
        "config_value": _json.dumps({"recipients": ["cfo@corp.in"], "active": False,
                                      "schedules": {}, "sections": [], "format": "email"})
    }
    resp = await client.get("/v1/cfo/digest/settings", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "digest_settings" in resp.json()


@pytest.mark.asyncio
async def test_cfo_digest_settings_put(client, mock_db):
    _set_auth(client)
    mock_db.execute.return_value = None
    body = {"recipients": ["cfo@corp.in"], "schedules": {}, "sections": [], "format": "email", "active": True}
    resp = await client.put("/v1/cfo/digest/settings", headers=AUTH_HEADER, json=body)
    assert resp.status_code == 200
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_cfo_digest_requires_auth(client):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={"sub": "x", "user_type": "oa_user", "role": "cfo",
                                          "tenant_id": "tenant-001", "jti": "s"})
    jwt.is_revoked = AsyncMock(return_value=True)
    resp = await client.get("/v1/cfo/digest/weekly", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)
