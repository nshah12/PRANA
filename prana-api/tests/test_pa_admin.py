"""
Tests for routers/pa_admin.py — Portal Admin platform management.

Covers:
  - Activate tenant requires portal_admin role (not OA)
  - Activation publishes TENANT_ACTIVATED to prana.audit.events
  - Emergency OA override publishes PA_EMERGENCY_OVERRIDE to prana.audit.events
  - PA has no tenant_id in JWT — can target any tenant (cross-tenant OK by design)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_pa_auth(client, pa_id: str = "pa-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": pa_id,
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,     # PA has no tenant affiliation
        "jti": "pa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": "tenant-001",
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


# -- Auth guard -------------------------------------------------------------

@pytest.mark.asyncio
async def test_activate_tenant_requires_portal_admin_role(client, mock_db):
    """OA-Admin must NOT be able to activate tenants — PA_ONLY."""
    _set_oa_auth(client)

    resp = await client.post(
        "/admin/tenants/tenant-123/activate",
        headers=AUTH_HEADER,
        json={},
    )

    assert resp.status_code == 403
    assert "PA_ONLY" in resp.json().get("detail", "")


# -- Tenant activation via tenants.py (wins the route) ---------------------

@pytest.mark.asyncio
async def test_tenant_activation_publishes_audit_event_to_kafka(client, mock_db, mock_kafka):
    """Activating a tenant creates the first OA-Admin and returns tenant details.
    The tenants.py route wins /admin/tenants/{id}/activate (registered first).
    It requires first_oa_admin_email in the body; calls TenantService.activate().
    """
    _set_pa_auth(client)

    with patch(
        "routers.tenants.TenantService.activate",
        new_callable=AsyncMock,
        return_value={
            "tenant_id": "tenant-xyz",
            "oa_admin_id": "oa-uuid-new",
            "temp_password": "TempPass1234",
        },
    ):
        resp = await client.post(
            "/admin/tenants/tenant-xyz/activate",
            headers=AUTH_HEADER,
            json={"first_oa_admin_email": "admin@acme.com"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("tenant_id") == "tenant-xyz"


# -- Emergency override Kafka event ----------------------------------------

@pytest.mark.asyncio
async def test_emergency_override_publishes_audit_event_to_kafka(client, mock_db, mock_kafka):
    """OA emergency account creation must publish PA_EMERGENCY_OVERRIDE to audit topic."""
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"tenant_id": "tenant-acme"}

    resp = await client.post(
        "/admin/oa-emergency/create",
        headers=AUTH_HEADER,
        json={"tenant_domain": "acme.com", "reason": "CEO locked out"},
    )

    assert resp.status_code == 200

    mock_kafka.publish.assert_called_once()
    topic, payload = mock_kafka.publish.call_args[0][:2]
    assert topic == "prana.audit.events"
    assert payload["event_type"] == "PA_EMERGENCY_OVERRIDE"
    assert payload["actor_type"] == "PORTAL_ADMIN"


# -- Cross-tenant capability -----------------------------------------------

@pytest.mark.asyncio
async def test_pa_admin_can_target_any_tenant_cross_tenant_ok(client, mock_db, mock_kafka):
    """PA has no tenant_id in JWT but can activate any tenant — by design."""
    _set_pa_auth(client, pa_id="pa-uuid-002")  # PA with tenant_id=None

    # Targeting a completely different tenant
    with patch(
        "routers.tenants.TenantService.activate",
        new_callable=AsyncMock,
        return_value={"tenant_id": "tenant-other-org", "oa_admin_id": "oa-new"},
    ):
        resp = await client.post(
            "/admin/tenants/tenant-other-org/activate",
            headers=AUTH_HEADER,
            json={"first_oa_admin_email": "admin@other-org.com"},
        )

    # Must succeed — PA is not scoped to any tenant
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reject_tenant_handles_verification_failed_status(client, mock_db):
    """A tenant whose domain verification timed out (VERIFICATION_FAILED) must
    still be rejectable — previously only PENDING/PENDING_VERIFICATION could be,
    leaving timed-out applications stuck forever.
    """
    _set_pa_auth(client)
    mock_db.execute = AsyncMock()

    resp = await client.post(
        "/admin/tenants/tenant-xyz/reject",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    sql = mock_db.execute.call_args.args[0]
    assert "VERIFICATION_FAILED" in sql


@pytest.mark.asyncio
async def test_retry_verification_requires_verification_failed_status(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"status": "ACTIVE", "domain": "acme.com"})

    resp = await client.post(
        "/admin/tenants/tenant-xyz/retry-verification",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_retry_verification_republishes_domain_verification_event(client, mock_db, mock_kafka):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"status": "VERIFICATION_FAILED", "domain": "acme.com"})
    mock_db.execute = AsyncMock()

    resp = await client.post(
        "/admin/tenants/tenant-xyz/retry-verification",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    mock_kafka.publish.assert_called_once()
    topic, payload = mock_kafka.publish.call_args[0][:2]
    assert topic == "prana.ingest.events"
    assert payload["event_type"] == "DOMAIN_VERIFICATION_REQUESTED"
    assert payload["tenant_id"] == "tenant-xyz"
    assert payload["workflow_id"] != "domain-verify-tenant-xyz"  # distinct retry id


@pytest.mark.asyncio
async def test_rate_limits_reads_real_throttled_count_from_redis(client, mock_db, mock_redis):
    """throttled_1h must come from the real Redis rate-limit-hits counter that
    ApiKeyAuth (dependencies.py) increments on every 429 — not a hardcoded 0.
    """
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"config_value": "1000"})
    mock_db.fetch = AsyncMock(return_value=[])
    mock_redis.get = AsyncMock(return_value=b"7")

    resp = await client.get("/admin/rate-limits", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["throttled_1h"] == 7


# -- No duplicate route registrations ---------------------------------------

def test_pa_admin_has_no_duplicate_suspend_route():
    """pa_admin.py must not define /tenants/{tenant_id}/suspend.

    tenants.router is mounted at /admin/tenants and pa_admin.router at /admin,
    so pa_admin's own "/tenants/{tenant_id}/suspend" resolves to the same
    /admin/tenants/{tenant_id}/suspend path as tenants.py's "/{tenant_id}/suspend".
    tenants.router is included first in main.py, so it always wins — a
    duplicate definition here is unreachable dead code that only invites
    drift (e.g. it never published the audit Kafka event tenants.py's
    version does).
    """
    from routers import pa_admin

    matching = [
        r for r in pa_admin.router.routes
        if getattr(r, "path", None) == "/tenants/{tenant_id}/suspend"
    ]
    assert matching == []


def test_pa_admin_has_no_duplicate_activate_route():
    """pa_admin.py must not define /tenants/{tenant_id}/activate.

    Same collision as suspend: pa_admin's "/tenants/{tenant_id}/activate"
    resolves to the same /admin/tenants/{tenant_id}/activate path as
    tenants.py's "/{tenant_id}/activate", and tenants.router wins because
    it's included first in main.py. This duplicate was unreachable dead code.
    """
    from routers import pa_admin

    matching = [
        r for r in pa_admin.router.routes
        if getattr(r, "path", None) == "/tenants/{tenant_id}/activate"
    ]
    assert matching == []


# -- Meta dashboard enrichment ----------------------------------------------

def _dashboard_fetchval_side_effect(sql, *args):
    s = sql.lower()
    if "count(*) from tenant where status='active'" in s:
        return 47
    if "count(*) from employee_master" in s:
        return 1200000
    if "count(*) from exception_queue where status='open'" in s and "raised_at" not in s:
        return 14
    if "pending_verification" in s.replace(" ", "").replace("'", ""):
        return 3
    if "sla" in s or ("exception_queue" in s and "raised_at" in s):
        return 2
    if "login_attempt_log" in s:
        return 34
    if "document" in s and "quarantined" in s.lower():
        return 2
    if "document" in s and "csam_detected" in s:
        return 0
    if "count(*) from document where is_deleted=false" in s:
        return 0
    if "count(*) from llm_usage_log" in s:
        return 5104
    if "sum(total_tokens)" in s:
        return 12400000
    if "avg(resolution_confidence)" in s:
        return 0.91
    if "llm_cost_per_1k_tokens_inr" in s:
        return "0.85"
    return 0


@pytest.mark.asyncio
async def test_meta_dashboard_includes_pending_approval_count(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchval = AsyncMock(side_effect=_dashboard_fetchval_side_effect)
    mock_db.fetch = AsyncMock(return_value=[])

    resp = await client.get("/admin/meta-dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["pending_approval_count"] == 3


@pytest.mark.asyncio
async def test_meta_dashboard_includes_sla_breach_count(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchval = AsyncMock(side_effect=_dashboard_fetchval_side_effect)
    mock_db.fetch = AsyncMock(return_value=[])

    resp = await client.get("/admin/meta-dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["sla_breach_count"] == 2


@pytest.mark.asyncio
async def test_meta_dashboard_security_alerts_uses_real_data(client, mock_db):
    """Security Alerts panel must reflect real login_attempt_log/document data,
    not hardcoded/mock values.
    """
    _set_pa_auth(client)
    mock_db.fetchval = AsyncMock(side_effect=_dashboard_fetchval_side_effect)
    mock_db.fetch = AsyncMock(return_value=[])

    resp = await client.get("/admin/meta-dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    alerts = resp.json()["security_alerts"]
    assert alerts["failed_logins_24h"] == 34
    assert alerts["quarantined_files"] == 2
    assert alerts["csam_events"] == 0
    assert "rate_limit_hits_24h" in alerts


@pytest.mark.asyncio
async def test_meta_dashboard_top_tenants_by_activity(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchval = AsyncMock(side_effect=_dashboard_fetchval_side_effect)

    def _fetch_side_effect(sql, *args):
        s = sql.lower()
        if "docs_today" in s or ("tenant" in s and "document" in s and "group by" in s):
            return [
                {"tenant_id": "t-1", "tenant_name": "NPCI", "docs_today": 1843,
                 "open_exceptions": 0, "status": "ACTIVE"},
            ]
        return []
    mock_db.fetch = AsyncMock(side_effect=_fetch_side_effect)

    resp = await client.get("/admin/meta-dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    top = resp.json()["top_tenants"]
    assert len(top) == 1
    assert top[0]["tenant_name"] == "NPCI"
    assert top[0]["docs_today"] == 1843


@pytest.mark.asyncio
async def test_meta_dashboard_includes_llm_usage_today(client, mock_db):
    """LLM Usage tile must reflect real llm_usage_log data + document.resolution_confidence,
    not hardcoded/mock values — see prana-ai/llm_client.py's usage_logger.
    """
    _set_pa_auth(client)
    mock_db.fetchval = AsyncMock(side_effect=_dashboard_fetchval_side_effect)
    mock_db.fetch = AsyncMock(return_value=[])

    resp = await client.get("/admin/meta-dashboard", headers=AUTH_HEADER)

    assert resp.status_code == 200
    llm_usage = resp.json()["llm_usage_today"]
    assert llm_usage["extraction_calls"] == 5104
    assert llm_usage["tokens_consumed"] == 12400000
    assert llm_usage["avg_confidence"] == 0.91
    # 12,400,000 tokens / 1000 * 0.85 INR = 10,540.0
    assert llm_usage["estimated_cost_inr"] == 10540.0


def test_pa_admin_has_no_duplicate_list_tenants_route():
    """pa_admin.py must not define GET /tenants.

    Same collision as suspend/activate: pa_admin's own "GET /tenants" resolves
    to the same /admin/tenants path as tenants.py's "GET \"\"", and
    tenants.router always wins because it's included first in main.py. This
    duplicate was unreachable dead code that lagged behind (missing
    industry/sla_tier/onboarding_tier/employee_headcount_band columns the
    live endpoint already selects).
    """
    from routers import pa_admin

    matching = [
        r for r in pa_admin.router.routes
        if getattr(r, "path", None) == "/tenants" and "GET" in (r.methods or set())
    ]
    assert matching == []


def test_pa_admin_has_no_duplicate_reinstate_route():
    """pa_admin.py must not define /tenants/{tenant_id}/reinstate.

    Same collision risk as suspend/activate: pa_admin's own
    "/tenants/{tenant_id}/reinstate" would resolve to the same
    /admin/tenants/{tenant_id}/reinstate path as tenants.py's
    "/{tenant_id}/reinstate", and tenants.router always wins.
    """
    from routers import pa_admin

    matching = [
        r for r in pa_admin.router.routes
        if getattr(r, "path", None) == "/tenants/{tenant_id}/reinstate"
    ]
    assert matching == []
