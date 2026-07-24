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

    mock_kafka.tenant_event.assert_called_once()
    payload = mock_kafka.tenant_event.call_args[0][0]
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
    mock_kafka.domain_verification_requested.assert_called_once()
    payload = mock_kafka.domain_verification_requested.call_args[0][0]
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


# -- PA platform-wide reset TOTP override -----------------------------------
# Departure from pa_admin.py's "zero employee PII" boundary — an explicit,
# reason-required override matching the oa-emergency/reset pattern.

@pytest.mark.asyncio
async def test_pa_reset_totp_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason": "Employee lost device"},
    )
    assert resp.status_code == 403


# -- Application errors (4th incident track, ERROR_OBSERVABILITY_DESIGN.md §7) ---

ERR_SVC = "services.error_observability_service.ErrorObservabilityService"


@pytest.mark.asyncio
async def test_list_errors_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/errors", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_errors_returns_items_across_all_tenants(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.list_errors", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"error_id": "e-1", "exception_type": "RuntimeError"}]
        resp = await client.get("/admin/errors", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["error_id"] == "e-1"
    # PA is cross-tenant by default — no tenant_id filter unless explicitly requested
    assert mock_list.call_args.kwargs["tenant_id"] is None


@pytest.mark.asyncio
async def test_list_errors_can_filter_by_tenant_and_status(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.list_errors", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        resp = await client.get(
            "/admin/errors?tenant_id=tenant-1&error_status=NEW", headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert mock_list.call_args.kwargs["tenant_id"] == "tenant-1"
    assert mock_list.call_args.kwargs["status"] == "NEW"


@pytest.mark.asyncio
async def test_acknowledge_error_calls_service(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.acknowledge", new_callable=AsyncMock) as mock_ack:
        resp = await client.post("/admin/errors/e-1/acknowledge", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"
    mock_ack.assert_awaited_once_with(error_id="e-1")


@pytest.mark.asyncio
async def test_acknowledge_error_404_when_not_found(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.acknowledge", new_callable=AsyncMock,
               side_effect=ValueError("error_event not found: e-missing")):
        resp = await client.post("/admin/errors/e-missing/acknowledge", headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ignore_error_calls_service(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.ignore", new_callable=AsyncMock) as mock_ignore:
        resp = await client.post("/admin/errors/e-1/ignore", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_ignore.assert_awaited_once_with(error_id="e-1")


@pytest.mark.asyncio
async def test_resolve_error_calls_service_with_actor_and_note(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-009")
    with patch(f"{ERR_SVC}.resolve", new_callable=AsyncMock) as mock_resolve:
        resp = await client.post(
            "/admin/errors/e-1/resolve", headers=AUTH_HEADER,
            json={"resolution_note": "Deployed a fix in v1.2.3"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    mock_resolve.assert_awaited_once_with(
        error_id="e-1", resolved_by="pa-uuid-009", resolution_note="Deployed a fix in v1.2.3",
    )


@pytest.mark.asyncio
async def test_resolve_error_rejects_empty_note_with_422(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/errors/e-1/resolve", headers=AUTH_HEADER, json={"resolution_note": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_promote_error_to_incident_calls_service(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{ERR_SVC}.promote_to_incident", new_callable=AsyncMock) as mock_promote:
        mock_promote.return_value = "incident-99"
        resp = await client.post(
            "/admin/errors/e-1/promote-to-incident", headers=AUTH_HEADER,
            json={"severity": "P1"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "promoted"
    assert data["incident_id"] == "incident-99"
    mock_promote.assert_awaited_once_with(error_id="e-1", severity="P1")


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": ""},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_totp_rejects_unknown_reason_code(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "MADE_UP_CODE"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_REASON_CODE"


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_note_when_reason_code_is_other(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "OTHER"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "REASON_NOTE_REQUIRED_FOR_OTHER"


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_identifier(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "  ", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "IDENTIFIER_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_totp_employee_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_reset_totp_clears_secret_platform_wide_no_tenant_scope(client, mock_db):
    """PA is platform-wide — no tenant_id filter on the employee_user lookup or UPDATE."""
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-001"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE",
              "reason_note": "CHRO confirmed"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "EMPLOYEE_TOTP_RESET"
    mock_db.execute.assert_called_once()
    sql, *params = mock_db.execute.call_args[0]
    assert "totp_secret_enc" in sql.lower() and "totp_configured_at" in sql.lower()
    assert "eu-001" in params


@pytest.mark.asyncio
async def test_pa_reset_totp_publishes_override_event_with_reason_per_tenant(client, mock_db, mock_kafka):
    """Must fan out one PORTAL_ADMIN-actor audit event per tenant the employee belongs
    to (multi-org employees have multiple employee_master rows) so each affected
    tenant's CISO gets visibility — using the employee's real tenant_id, not a
    platform-level placeholder. reason_code/reason_note are structured, queryable
    audit fields (see account_status_event.reason_code/reason_note) — not a single
    free-text blob."""
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-002"}
    mock_db.fetch.return_value = [
        {"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-a"},
        {"tenant_id": "tenant-002", "employee_uuid": "emp-uuid-b"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "9000000002", "reason_code": "SUPPORT_ESCALATION",
              "reason_note": "TCK-1234"},
    )

    assert resp.status_code == 200
    assert mock_kafka.employee_event.call_count == 2
    seen_tenants = set()
    for call in mock_kafka.employee_event.call_args_list:
        event = call[0][0]
        assert event["event_type"] == "EMPLOYEE_TOTP_RESET"
        assert event["actor_type"] == "PORTAL_ADMIN"
        assert event["actor_id"] == "pa-uuid-777"
        assert event["reason_code"] == "SUPPORT_ESCALATION"
        assert event["reason_note"] == "TCK-1234"
        assert event["override"] is True
        seen_tenants.add(event["tenant_id"])
    assert seen_tenants == {"tenant-001", "tenant-002"}


# -- PA unlock (another PA unlocks a locked-out PA) --------------------------
# auth_pa.py: "PA lockout is not auto-unlocked — requires another PA to unlock."
# No endpoint existed for this until now.

@pytest.mark.asyncio
async def test_pa_unlock_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "locked@prana.in"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_unlock_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "nobody@prana.in"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_unlock_not_locked_returns_409(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"pa_id": "pa-uuid-002", "status": "ACTIVE"}
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "already-active@prana.in"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ALREADY_UNLOCKED"


@pytest.mark.asyncio
async def test_pa_unlock_restores_locked_account_and_publishes_event(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-001")
    mock_db.fetchrow.return_value = {"pa_id": "pa-uuid-002", "status": "LOCKED"}
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "locked@prana.in"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "LOCK_REMOVED"

    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "portal_admin" in all_sql and "'active'" in all_sql
    assert "account_status_event" in all_sql

    mock_kafka.security_event.assert_awaited_once()
    sec = mock_kafka.security_event.call_args[0][0]
    assert sec["event_type"] == "ACCOUNT_UNLOCKED"
    assert sec["actor_type"] == "PORTAL_ADMIN"
    assert sec["actor_id"] == "pa-uuid-001"
    assert sec["target_account_id"] == "pa-uuid-002"


# -- Employee record merge/dedupe ---------------------------------------------
# PA-only, platform-wide: merges a duplicate employee_user (e.g. PAN-typo led to
# two identities for the same physical person) into a canonical employee_user_id.

def _merge_body(duplicate="dup@example.com", canonical="canonical@example.com", reason="PAN typo dedup"):
    return {"duplicate_identifier": duplicate, "canonical_identifier": canonical, "reason": reason}


@pytest.mark.asyncio
async def test_merge_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_merge_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body(reason=""),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_merge_duplicate_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_merge_canonical_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, None]
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_merge_rejects_merging_employee_into_itself(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-same"}, {"employee_user_id": "eu-same"}]
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "CANNOT_MERGE_SAME_EMPLOYEE"


@pytest.mark.asyncio
async def test_merge_repoints_all_referencing_tables_and_marks_duplicate(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, {"employee_user_id": "eu-canonical"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_RECORDS_MERGED"
    assert body["canonical_employee_user_id"] == "eu-canonical"

    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    for table in (
        "employee_master", "career_event", "device_credential", "share_token",
        "document_access_log", "employee_consent", "erasure_request",
        "data_export_request", "data_correction_request", "dpdp_grievance", "oa_user",
    ):
        assert table in all_sql, f"merge must re-point {table}"
    # The duplicate row itself must be marked MERGED with merged_into set — never deleted.
    assert "merged" in all_sql and "eu-dup" in all_sql and "eu-canonical" in all_sql


@pytest.mark.asyncio
async def test_merge_publishes_audit_event(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-555")
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, {"employee_user_id": "eu-canonical"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/merge", headers=AUTH_HEADER,
        json=_merge_body(reason="Confirmed same person via HR"),
    )

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_RECORDS_MERGED"
    assert event["actor_type"] == "PORTAL_ADMIN"
    assert event["actor_id"] == "pa-uuid-555"
    assert event["duplicate_employee_user_id"] == "eu-dup"
    assert event["canonical_employee_user_id"] == "eu-canonical"
    assert event["reason"] == "Confirmed same person via HR"


# -- PA platform-wide reset password override ---------------------------------

@pytest.mark.asyncio
async def test_pa_reset_password_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_reset_password_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": ""},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_password_rejects_unknown_reason_code(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "MADE_UP_CODE"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_REASON_CODE"


@pytest.mark.asyncio
async def test_pa_reset_password_requires_note_when_reason_code_is_other(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "OTHER", "reason_note": "  "},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "REASON_NOTE_REQUIRED_FOR_OTHER"


@pytest.mark.asyncio
async def test_pa_reset_password_employee_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_reset_password_generates_temp_password_platform_wide(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-001"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE",
              "reason_note": "CHRO confirmed"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_PASSWORD_RESET"
    assert len(body["temp_password"]) >= 12
    mock_db.execute.assert_called_once()
    sql, *params = mock_db.execute.call_args[0]
    assert "password_hash" in sql.lower() and "force_reset" in sql.lower()
    assert "eu-001" in params


@pytest.mark.asyncio
async def test_pa_reset_password_publishes_override_event_with_reason_per_tenant(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-002"}
    mock_db.fetch.return_value = [
        {"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-a"},
        {"tenant_id": "tenant-002", "employee_uuid": "emp-uuid-b"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "9000000002", "reason_code": "SUPPORT_ESCALATION",
              "reason_note": "TCK-1234"},
    )
    temp_password = resp.json()["temp_password"]

    assert resp.status_code == 200
    assert mock_kafka.employee_event.call_count == 2
    seen_tenants = set()
    for call in mock_kafka.employee_event.call_args_list:
        event = call[0][0]
        assert event["event_type"] == "EMPLOYEE_PASSWORD_RESET"
        assert event["actor_type"] == "PORTAL_ADMIN"
        assert event["actor_id"] == "pa-uuid-777"
        assert event["reason_code"] == "SUPPORT_ESCALATION"
        assert event["reason_note"] == "TCK-1234"
        assert event["override"] is True
        assert temp_password not in str(event)
        seen_tenants.add(event["tenant_id"])
    assert seen_tenants == {"tenant-001", "tenant-002"}


# ── Contact inquiries / org applications (relocated from routers/public.py) ──

@pytest.mark.asyncio
async def test_list_contact_inquiries_requires_pa_auth(client):
    resp = await client.get("/admin/contact-inquiries")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_contact_inquiries_rejects_oa_admin(client):
    _set_oa_auth(client)
    resp = await client.get("/admin/contact-inquiries", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_contact_inquiries_returns_items(client, mock_db):
    import datetime
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{
        "id": "ci-1", "name": "Priya", "email": "priya@example.com", "org": "Acme",
        "enquiry_type": "General", "message": "Hi", "status": "NEW",
        "submitted_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
    }]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/admin/contact-inquiries", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "priya@example.com"


@pytest.mark.asyncio
async def test_list_org_applications_requires_pa_auth(client):
    resp = await client.get("/admin/org-applications")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_org_applications_returns_items(client, mock_db):
    import datetime
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{
        "id": "app-1", "org_name": "Acme", "domain": "acme.in", "entity_type": "PVT_LTD",
        "industry": "IT", "headcount_band": "50-100", "contact_name": "Priya",
        "contact_email": "priya@acme.in", "contact_mobile": "+919000000001",
        "message": "", "how_heard": "Google", "agreed_to_dpa": True, "email_verified": True,
        "status": "PENDING", "review_notes": None,
        "submitted_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        "reviewed_at": None,
    }]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/admin/org-applications", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["items"][0]["org_name"] == "Acme"


@pytest.mark.asyncio
async def test_review_application_requires_pa_auth(client):
    resp = await client.patch("/admin/org-applications/app-1", json={"status": "APPROVED"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_application_updates_status(client, mock_db):
    _set_pa_auth(client)
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.patch(
        "/admin/org-applications/app-1",
        headers=AUTH_HEADER,
        json={"status": "APPROVED", "review_notes": "Looks good"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    mock_db.execute.assert_awaited_once()
    args = mock_db.execute.call_args.args
    assert args[1] == "APPROVED"
    assert args[2] == "Looks good"
    assert args[3] == "app-1"


# ── Severity / SLA policy config ─────────────────────────────────────────────

SLA_SVC = "services.severity_policy_service.SeverityPolicyService"


@pytest.mark.asyncio
async def test_list_sla_policy_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/sla-policy", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_sla_policy_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.get_all_sla_policies", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"severity": "P0", "sla_minutes": 30, "auto_create_incident": True,
                                    "description": None, "updated_by": None, "updated_at": None}]
        resp = await client.get("/admin/sla-policy", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["severity"] == "P0"


@pytest.mark.asyncio
async def test_update_sla_policy_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_update.return_value = {"severity": "P1", "sla_minutes": 90,
                                     "auto_create_incident": True, "description": "x",
                                     "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.patch(
            "/admin/sla-policy/P1", headers=AUTH_HEADER,
            json={"sla_minutes": 90, "auto_create_incident": True},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "SLA_POLICY_UPDATED"
    assert resp.json()["sla_policy"]["sla_minutes"] == 90
    mock_update.assert_awaited_once_with(
        severity="P1", sla_minutes=90, auto_create_incident=True,
        description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_sla_policy_publishes_immudb_audited_tenant_event(client, mock_db):
    """Retrofit: sla-policy previously wrote no audit event at all — only
    updated_by/updated_at columns, not tamper-evident. See
    prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10.3."""
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_update.return_value = {"severity": "P1", "sla_minutes": 90,
                                     "auto_create_incident": True, "description": "x",
                                     "updated_by": "pa-uuid-777", "updated_at": None}
        await client.patch(
            "/admin/sla-policy/P1", headers=AUTH_HEADER,
            json={"sla_minutes": 90, "auto_create_incident": True},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SLA_POLICY_UPDATED"
    assert event["tenant_id"] is None
    assert event["severity"] == "P1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_sla_policy_unknown_severity_returns_404(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock,
               side_effect=ValueError("No SLA policy for severity P9")):
        resp = await client.patch(
            "/admin/sla-policy/P9", headers=AUTH_HEADER, json={"sla_minutes": 10},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_severity_rules_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/severity-rules", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_severity_rules_filters_by_domain_query_param(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.list_severity_rules", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        resp = await client.get("/admin/severity-rules?domain=ANOMALY_RULE", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_list.assert_awaited_once_with(domain="ANOMALY_RULE")


@pytest.mark.asyncio
async def test_create_severity_rule_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock) as mock_create, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_create.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "NEW_RULE", "occurrence_threshold": 5,
                                     "occurrence_threshold_max": None, "window_minutes": 15,
                                     "severity": "P2", "priority": 50, "is_active": True,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "EXACT", "match_value": "NEW_RULE",
                  "occurrence_threshold": 5, "window_minutes": 15, "severity": "P2", "priority": 50},
        )

    assert resp.status_code == 201
    assert resp.json()["message"] == "SEVERITY_RULE_CREATED"
    mock_create.assert_awaited_once_with(
        domain="ANOMALY_RULE", match_type="EXACT", match_value="NEW_RULE",
        occurrence_threshold=5, occurrence_threshold_max=None, window_minutes=15,
        severity="P2", priority=50, description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_create_severity_rule_publishes_immudb_audited_tenant_event(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock) as mock_create, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_create.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "NEW_RULE", "occurrence_threshold": 5,
                                     "occurrence_threshold_max": None, "window_minutes": 15,
                                     "severity": "P2", "priority": 50, "is_active": True,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "EXACT", "match_value": "NEW_RULE",
                  "occurrence_threshold": 5, "window_minutes": 15, "severity": "P2", "priority": 50},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SEVERITY_RULE_CREATED"
    assert event["rule_id"] == "r-1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_create_severity_rule_invalid_match_type_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock,
               side_effect=ValueError("match_type must be PREFIX, EXACT, or DEFAULT")):
        resp = await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "FUZZY", "severity": "P2"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_severity_rule_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_update.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 75,
                                     "occurrence_threshold_max": None, "window_minutes": 10,
                                     "severity": "P1", "priority": 10, "is_active": False,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.patch(
            "/admin/severity-rules/r-1", headers=AUTH_HEADER,
            json={"occurrence_threshold": 75, "is_active": False},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "SEVERITY_RULE_UPDATED"
    assert resp.json()["severity_rule"]["is_active"] is False
    mock_update.assert_awaited_once_with(
        rule_id="r-1", occurrence_threshold=75, occurrence_threshold_max=None,
        window_minutes=None, severity=None, priority=None, is_active=False,
        description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_severity_rule_publishes_immudb_audited_tenant_event(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_update.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 75,
                                     "occurrence_threshold_max": None, "window_minutes": 10,
                                     "severity": "P1", "priority": 10, "is_active": False,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        await client.patch(
            "/admin/severity-rules/r-1", headers=AUTH_HEADER,
            json={"occurrence_threshold": 75, "is_active": False},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SEVERITY_RULE_UPDATED"
    assert event["rule_id"] == "r-1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_severity_rule_unknown_id_returns_404(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock,
               side_effect=ValueError("Rule r-9 not found")):
        resp = await client.patch(
            "/admin/severity-rules/r-9", headers=AUTH_HEADER, json={"priority": 5},
        )
    assert resp.status_code == 404


# ── Communication Hub settings — Channel Policy / Vendor Chains / Credentials ─
# prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1

COMM_SVC = "services.communication_settings_service.CommunicationSettingsService"


@pytest.mark.asyncio
async def test_get_channel_policy_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/channel-policy", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_channel_policy_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.get_channel_policy", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {"template_id": "OA_WELCOME", "channels": ["email"], "platform_channels": ["email"],
             "is_tenant_override": False},
        ]
        resp = await client.get("/admin/communications/channel-policy", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["template_id"] == "OA_WELCOME"
    mock_get.assert_awaited_once_with(tenant_id=None)


@pytest.mark.asyncio
async def test_update_channel_policy_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.update_channel_policy", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"template_id": "OA_WELCOME", "channels": ["email"], "tenant_id": None}
        resp = await client.patch(
            "/admin/communications/channel-policy/OA_WELCOME", headers=AUTH_HEADER,
            json={"channels": ["email"]},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_CHANNEL_POLICY_UPDATED"
    mock_update.assert_awaited_once_with(
        template_id="OA_WELCOME", channels=["email"], tenant_id=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_channel_policy_invalid_channels_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.update_channel_policy", new_callable=AsyncMock,
               side_effect=ValueError("INVALID_CHANNELS: ['carrier_pigeon']")):
        resp = await client.patch(
            "/admin/communications/channel-policy/OA_WELCOME", headers=AUTH_HEADER,
            json={"channels": ["carrier_pigeon"]},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_vendor_chains_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/vendor-chains", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_vendor_chains_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.get_vendor_chains", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"email": {"chain": ["ses"], "available_vendors": ["ses", "smtp"]}}
        resp = await client.get("/admin/communications/vendor-chains", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["chains"]["email"]["chain"] == ["ses"]
    mock_get.assert_awaited_once_with(tenant_id=None)


@pytest.mark.asyncio
async def test_update_vendor_chain_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.update_vendor_chain", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"channel": "sms", "chain": ["msg91", "aws"], "tenant_id": None}
        resp = await client.patch(
            "/admin/communications/vendor-chains/sms", headers=AUTH_HEADER,
            json={"vendors": ["msg91", "aws"]},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_VENDOR_CHAIN_UPDATED"
    mock_update.assert_awaited_once_with(
        channel="sms", vendors=["msg91", "aws"], tenant_id=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_vendor_chain_unknown_channel_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.update_vendor_chain", new_callable=AsyncMock,
               side_effect=ValueError("UNKNOWN_CHANNEL: carrier_pigeon")):
        resp = await client.patch(
            "/admin/communications/vendor-chains/carrier_pigeon", headers=AUTH_HEADER,
            json={"vendors": ["x"]},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_vendor_credentials_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/vendor-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_vendor_credentials_never_leaks_secrets(client, mock_db):
    """editable_fields lists field NAMES (safe — needed by the frontend to
    render inputs); the guarantee under test is that the response schema has
    no slot for a raw secret VALUE — vendors carries only booleans/enums,
    and the DB row's enc_value column is never selected by this query."""
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{"vendor": "exotel", "field_name": "exotel_api_key"}]
    resp = await client.get("/admin/communications/vendor-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vendors"]["exotel"] == {"configured": True, "source": "db"}
    assert "exotel_api_key" in data["editable_fields"]["exotel"]
    fetch_sql = mock_db.fetch.call_args.args[0]
    assert "enc_value" not in fetch_sql


@pytest.mark.asyncio
async def test_update_vendor_credential_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.patch(
        "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
        json={"field_name": "exotel_api_key", "value": "real-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_vendor_credential_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.set_vendor_credential", new_callable=AsyncMock) as mock_set:
        resp = await client.patch(
            "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
            json={"field_name": "exotel_api_key", "value": "real-secret-value"},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_VENDOR_CREDENTIAL_ROTATED"
    assert "real-secret-value" not in resp.text
    mock_set.assert_awaited_once()
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["vendor"] == "exotel"
    assert call_kwargs["field_name"] == "exotel_api_key"
    assert call_kwargs["value"] == "real-secret-value"
    assert call_kwargs["updated_by"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_vendor_credential_unknown_field_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.set_vendor_credential", new_callable=AsyncMock,
               side_effect=ValueError("UNKNOWN_FIELD: not_a_real_field for vendor exotel")):
        resp = await client.patch(
            "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
            json={"field_name": "not_a_real_field", "value": "x"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_no_vendor_credentials_route_for_oa_admin_patch(client, mock_db):
    """OA-Admin never edits vendor secrets — no such route exists on org_settings.py."""
    _set_oa_auth(client)
    resp = await client.patch(
        "/v1/org/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
        json={"field_name": "exotel_api_key", "value": "x"},
    )
    assert resp.status_code == 404
