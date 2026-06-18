"""
Tests for routers/chro.py — CHRO role endpoints.

Mandatory coverage per TDD rules:
  1. Auth test    — unauthenticated returns 401/403
  2. Role test    — wrong role returns 403
  3. Tenant iso   — cannot access another tenant's data
  4. Happy path   — correct input returns expected shape
  5. Privacy test — response contains no raw salary figures (₹ or 'salary' keys)

Auth strategy: configure app.state.jwt_service mock to control what the JWT
decodes to, rather than patching require_oa (which is evaluated at import time).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Auth helpers ──────────────────────────────────────────────────────────────

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "chro", tenant_id: str = "tenant-001") -> None:
    """Configure jwt_service mock so the request authenticates as the given role."""
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub":       f"{role}-uuid-001",
        "user_type": "oa_user",
        "role":      role,
        "tenant_id": tenant_id,
        "jti":       "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _revoke_all(client) -> None:
    """Return to default deny — simulates a revoked/expired session."""
    jwt = client.app.state.jwt_service
    # Must provide a valid-shaped payload so _decode_bearer can access payload["jti"]
    # before the is_revoked check raises 401.
    jwt.decode = MagicMock(return_value={
        "sub": "revoked-user", "user_type": "oa_user", "role": "chro",
        "tenant_id": "tenant-001", "jti": "revoked-session",
    })
    jwt.is_revoked = AsyncMock(return_value=True)


# ── 1. Auth guard — unauthenticated is denied ─────────────────────────────────

@pytest.mark.asyncio
async def test_vault_health_requires_auth(client):
    """No valid JWT → 401."""
    _revoke_all(client)
    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_compliance_requires_auth(client):
    _revoke_all(client)
    resp = await client.get("/v1/chro/compliance", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_statutory_coverage_requires_auth(client):
    _revoke_all(client)
    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_compliance_posture_requires_auth(client):
    _revoke_all(client)
    resp = await client.get("/v1/chro/compliance-posture", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# ── 2. Role guard — wrong role is denied ─────────────────────────────────────

@pytest.mark.asyncio
async def test_vault_health_rejects_oa_operator(client, mock_db):
    """oa_operator must not access CHRO endpoints — wrong role."""
    _set_auth(client, role="oa_operator")
    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_vault_health_rejects_cfo_role(client, mock_db):
    _set_auth(client, role="cfo")
    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_alert_config_rejects_ciso_role(client, mock_db):
    _set_auth(client, role="ciso")
    resp = await client.get("/v1/chro/alerts/config", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_oa_admin_can_access_chro_endpoints(client, mock_db):
    """oa_admin is allowed — CHRO = Depends(require_oa('chro', 'oa_admin'))."""
    _set_auth(client, role="oa_admin")
    mock_db.fetchrow.return_value = {
        "overall_score": 80, "employment_proof_score": 85,
        "salary_slip_score": 70, "form16_score": 65, "total_gaps": 10,
    }
    mock_db.fetch.return_value = []
    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)
    assert resp.status_code == 200


# ── 3. Tenant isolation ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vault_health_tenant_isolation(client, mock_db):
    """
    DB queries must be scoped to the JWT tenant_id, not a tenant from
    any request parameter or body.
    """
    _set_auth(client, role="chro", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {
        "overall_score": 80, "employment_proof_score": 85,
        "salary_slip_score": 70, "form16_score": 65, "total_gaps": 10,
    }
    mock_db.fetch.return_value = []

    await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)

    all_calls = mock_db.fetchrow.call_args_list + mock_db.fetch.call_args_list
    assert any("tenant-001" in str(c) for c in all_calls), \
        "DB was not scoped to tenant-001 — tenant isolation not enforced"


@pytest.mark.asyncio
async def test_statutory_coverage_tenant_isolation(client, mock_db):
    """Coverage queries must be scoped to tenant from JWT, not request body."""
    _set_auth(client, role="chro", tenant_id="tenant-XYZ")
    mock_db.fetchval.return_value = 50

    await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    all_val_calls = str(mock_db.fetchval.call_args_list)
    assert "tenant-XYZ" in all_val_calls, \
        "statutory-coverage DB call did not use JWT tenant_id"


# ── 4. Happy path — response shape contracts ──────────────────────────────────

@pytest.mark.asyncio
async def test_vault_health_happy_path(client, mock_db):
    _set_auth(client)
    mock_db.fetchrow.return_value = {
        "overall_score": 82, "employment_proof_score": 90,
        "salary_slip_score": 75, "form16_score": 60, "total_gaps": 12,
    }
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "by_department" in data
    assert "gaps" in data
    assert isinstance(data["by_department"], list)


@pytest.mark.asyncio
async def test_compliance_calendar_shape(client, mock_db):
    """Response must include items list, total count, and overdue count."""
    _set_auth(client)
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/chro/compliance", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "overdue" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_statutory_coverage_shape(client, mock_db):
    """Response must include acts, active_employees, current_fy, overall_risk."""
    _set_auth(client)
    mock_db.fetchval.return_value = 100

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "acts" in data
    assert "active_employees" in data
    assert "current_fy" in data
    assert "overall_risk" in data
    assert data["overall_risk"] in ("LOW", "MEDIUM", "HIGH")


@pytest.mark.asyncio
async def test_statutory_coverage_each_act_has_required_audit_fields(client, mock_db):
    """
    Each act entry must expose statutory reference, coverage %, gap count,
    and severity — the minimum an auditor needs to assess compliance.
    """
    _set_auth(client)
    mock_db.fetchval.return_value = 50

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    acts = resp.json()["acts"]
    assert len(acts) >= 4, "Expected at least 4 statutory acts (IT, Wages, EPF, Shops)"
    for act in acts:
        assert "act" in act,          f"Missing 'act' in {act}"
        assert "section" in act,      f"Missing 'section' in {act}"
        assert "obligation" in act,   f"Missing 'obligation' in {act}"
        assert "coverage_pct" in act, f"Missing 'coverage_pct' in {act}"
        assert "gap_count" in act,    f"Missing 'gap_count' in {act}"
        assert "severity" in act,     f"Missing 'severity' in {act}"
        assert act["severity"] in ("LOW", "MEDIUM", "HIGH")


@pytest.mark.asyncio
async def test_compliance_posture_shape(client, mock_db):
    """DPDP posture response: 4 KPIs + checklist array + action_items."""
    _set_auth(client)
    mock_db.fetchval.return_value = 80
    mock_db.fetchrow.side_effect = [
        {"score": 78},
        {"config_value": "Nilesh Shah"},
        {"data_residency_verified": True},
    ]

    resp = await client.get("/v1/chro/compliance-posture", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "overall_risk" in data
    assert "consent_pct" in data
    assert "vault_completeness_pct" in data
    assert "erasure_sla_pct" in data
    assert "grievance_resolved_pct" in data
    assert "checklist" in data
    assert "action_items" in data
    assert isinstance(data["checklist"], list)
    assert len(data["checklist"]) >= 4


@pytest.mark.asyncio
async def test_compliance_posture_checklist_has_statutory_refs(client, mock_db):
    """Every checklist item must carry a statutory_ref so auditors can trace the obligation."""
    _set_auth(client)
    mock_db.fetchval.return_value = 95
    mock_db.fetchrow.side_effect = [
        {"score": 88},
        {"config_value": "Nilesh Shah"},
        {"data_residency_verified": True},
    ]

    resp = await client.get("/v1/chro/compliance-posture", headers=AUTH_HEADER)

    checklist = resp.json()["checklist"]
    for item in checklist:
        assert "statutory_ref" in item, f"Missing statutory_ref in checklist item: {item}"
        assert item["statutory_ref"], "statutory_ref must not be empty"


@pytest.mark.asyncio
async def test_alert_config_get_returns_all_keys(client, mock_db):
    """GET alert config: returns a dict with a bool for every alert type."""
    _set_auth(client)
    mock_db.fetch.return_value = [
        {"config_key": "chro_alert_deadline_alert",    "config_value": "true"},
        {"config_key": "chro_alert_vault_health_drop", "config_value": "false"},
    ]

    resp = await client.get("/v1/chro/alerts/config", headers=AUTH_HEADER)

    assert resp.status_code == 200
    config = resp.json()["config"]
    assert isinstance(config, dict)
    # All 5 keys must be present (missing keys get defaults)
    for key in ["deadline_alert", "vault_health_drop", "exception_spike",
                "exit_doc_delay", "security_anomaly"]:
        assert key in config, f"Missing alert key: {key}"
    assert config["deadline_alert"] is True
    assert config["vault_health_drop"] is False


@pytest.mark.asyncio
async def test_alert_config_save_persists(client, mock_db):
    """PATCH alert config must write to DB via transaction."""
    _set_auth(client)

    resp = await client.patch("/v1/chro/alerts/config", headers=AUTH_HEADER, json={
        "config": {
            "deadline_alert":    True,
            "vault_health_drop": False,
            "exception_spike":   True,
            "exit_doc_delay":    False,
            "security_anomaly":  False,
        }
    })

    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    # DB was touched — executemany, execute, or transaction context started
    assert (mock_db.execute.called or mock_db.executemany.called or mock_db.transaction.called), \
        "Expected at least one DB write for alert config save"


@pytest.mark.asyncio
async def test_alert_config_ignores_unknown_keys(client, mock_db):
    """Unknown keys in the PATCH body must not be written to DB."""
    _set_auth(client)

    await client.patch("/v1/chro/alerts/config", headers=AUTH_HEADER, json={
        "config": {
            "deadline_alert":          True,
            "unknown_malicious_key":   True,   # not in ALERT_KEYS
        }
    })

    all_execute_calls = str(mock_db.execute.call_args_list)
    assert "unknown_malicious_key" not in all_execute_calls


@pytest.mark.asyncio
async def test_weekly_digest_shape(client, mock_db):
    _set_auth(client)
    mock_db.fetchval.side_effect = [5, 2]
    mock_db.fetchrow.side_effect = [
        {"score": 78},
        {
            "obligation_name": "Form 16 issuance",
            "statutory_ref":   "IT Act 1961, S.203",
            "deadline":        "2025-06-15",
            "status":          "PENDING",
        },
    ]

    resp = await client.get("/v1/chro/digest/weekly", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "docs_pushed_this_week" in data
    assert "open_exceptions" in data
    # next_deadline must be an object (not a string) — changed in audit-grade version
    if data["next_deadline"] is not None:
        assert "statutory_ref" in data["next_deadline"]
        assert "deadline" in data["next_deadline"]


@pytest.mark.asyncio
async def test_monthly_summary_shape(client, mock_db):
    _set_auth(client)
    mock_db.fetchval.side_effect = [120, 40, 35, 3, 2]
    mock_db.fetchrow.return_value = {"score": 80}

    resp = await client.get("/v1/chro/digest/monthly", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert "vault_health_current" in data
    assert "docs_pushed" in data
    assert "docs_pushed_prev" in data
    assert "active_employees" in data
    assert "open_exceptions" in data
    assert "overdue_obligations" in data


# ── 5. Privacy contract — no raw ₹ salary figures ────────────────────────────

def _has_raw_salary(data: dict | list) -> bool:
    """Recursively check for keys that suggest raw salary ₹ figures."""
    FORBIDDEN = {"salary", "ctc", "salary_inr", "payroll_total", "ctc_annual"}
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in FORBIDDEN:
                return True
            if _has_raw_salary(v):
                return True
    elif isinstance(data, list):
        return any(_has_raw_salary(item) for item in data)
    return False


@pytest.mark.asyncio
async def test_vault_health_no_raw_salary(client, mock_db):
    """vault-health response must contain scores only — never raw ₹ figures."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {
        "overall_score": 82, "employment_proof_score": 90,
        "salary_slip_score": 75, "form16_score": 60, "total_gaps": 12,
    }
    mock_db.fetch.return_value = []

    resp = await client.get("/v1/chro/vault-health", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert not _has_raw_salary(resp.json()), \
        "vault-health response contains a raw salary key — privacy violation"


@pytest.mark.asyncio
async def test_statutory_coverage_no_raw_salary(client, mock_db):
    """Coverage response: employee counts and percentages only — no ₹ amounts."""
    _set_auth(client)
    mock_db.fetchval.return_value = 200

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert not _has_raw_salary(resp.json()), \
        "statutory-coverage response leaks salary data — privacy violation"


@pytest.mark.asyncio
async def test_compliance_posture_no_raw_salary(client, mock_db):
    _set_auth(client)
    mock_db.fetchval.return_value = 90
    mock_db.fetchrow.side_effect = [
        {"score": 88},
        {"config_value": "Test Officer"},
        {"data_residency_verified": True},
    ]

    resp = await client.get("/v1/chro/compliance-posture", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert not _has_raw_salary(resp.json()), \
        "compliance-posture response leaks salary data — privacy violation"


# ── Statutory coverage business logic ────────────────────────────────────────

@pytest.mark.asyncio
async def test_statutory_severity_high_when_form16_below_70_pct(client, mock_db):
    """
    If Form 16 coverage < 70%, severity must be HIGH.
    A Labour Inspector finding at 50% coverage would result in penalty under IT Act.
    """
    _set_auth(client)
    # 100 employees, 50 have Form 16 → 50% → HIGH
    mock_db.fetchval.side_effect = [100, 50, 90, 80, 95, 0]

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    acts = resp.json()["acts"]
    form16_act = next(a for a in acts if "Income Tax" in a["act"])
    assert form16_act["severity"] == "HIGH", \
        f"Expected HIGH severity at 50% Form 16 coverage, got {form16_act['severity']}"
    assert resp.json()["overall_risk"] == "HIGH"


@pytest.mark.asyncio
async def test_statutory_overall_low_when_fully_compliant(client, mock_db):
    """100% coverage on all obligations → overall_risk = LOW."""
    _set_auth(client)
    mock_db.fetchval.side_effect = [100, 100, 100, 100, 100, 0]

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["overall_risk"] == "LOW"


@pytest.mark.asyncio
async def test_statutory_coverage_empty_org_no_division_error(client, mock_db):
    """0 active employees must return empty acts list, not divide-by-zero."""
    _set_auth(client)
    mock_db.fetchval.return_value = 0

    resp = await client.get("/v1/chro/statutory-coverage", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["active_employees"] == 0
    assert resp.json()["acts"] == []
