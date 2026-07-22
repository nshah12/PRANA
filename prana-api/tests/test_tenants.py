"""
Tests for routers/tenants.py — PA-only tenant management.

Covers:
  - Create tenant requires portal_admin (not OA, not employee)
  - POST create_tenant publishes DOMAIN_VERIFICATION_REQUESTED to Kafka (not direct workflow start)
  - GET list_tenants returns {"tenants": [...]} — never bare array
"""
from unittest.mock import AsyncMock, MagicMock, patch
import datetime

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}

_MIN_TENANT_BODY = {
    "tenant_name": "Acme Corp Pvt Ltd",
    "domain": "acme.com",
    "primary_state": "Maharashtra",
    "first_oa_admin_email": "admin@acme.com",
    "home_region": "ap-south-1",
}


def _set_pa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "pa-uuid-001",
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,
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


def _make_tenant_row():
    return {
        "tenant_id": "tenant-uuid-001",
        "tenant_name": "Acme Corp",
        "domain": "acme.com",
        "status": "ACTIVE",
        "home_region": "ap-south-1",
        "primary_state": "Maharashtra",
        "created_at": datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        "cin": None,
        "gstin": None,
        "storage_quota_gb": 50,
    }


# -- Auth guard ------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tenant_requires_portal_admin(client, mock_db):
    """OA-Admin must not be able to create tenants — PA route only."""
    _set_oa_auth(client)

    resp = await client.post(
        "/admin/tenants",
        headers=AUTH_HEADER,
        json=_MIN_TENANT_BODY,
    )

    assert resp.status_code == 403


# -- Kafka instead of direct workflow start --------------------------------

@pytest.mark.asyncio
async def test_domain_verification_publishes_to_kafka_not_direct_workflow(
    client, mock_db, mock_kafka
):
    """POST /admin/tenants must publish DOMAIN_VERIFICATION_REQUESTED to Kafka.
    WorkflowConsumer (not the HTTP handler) starts DomainVerificationWorkflow.
    """
    _set_pa_auth(client)

    # TenantService.create_pending() calls db.execute — mock it
    mock_db.execute = AsyncMock(return_value=None)

    with patch(
        "routers.tenants.TenantService.create_pending",
        new_callable=AsyncMock,
        return_value={"tenant_id": "new-tenant-uuid", "status": "PENDING"},
    ):
        resp = await client.post(
            "/admin/tenants",
            headers=AUTH_HEADER,
            json=_MIN_TENANT_BODY,
        )

    assert resp.status_code == 201

    # Kafka must have been called with DOMAIN_VERIFICATION_REQUESTED — via the
    # domain_verification_requested() helper (publishes to TOPIC_INGEST so
    # WorkflowConsumer actually picks it up; tenant_event() alone would not).
    mock_kafka.domain_verification_requested.assert_called_once()
    payload = mock_kafka.domain_verification_requested.call_args[0][0]
    assert payload["event_type"] == "DOMAIN_VERIFICATION_REQUESTED"
    assert "tenant_id" in payload


# -- Suspend publishes audit event, never writes audit_event directly ------

@pytest.mark.asyncio
async def test_suspend_tenant_publishes_audit_event_to_kafka(client, mock_db, mock_kafka):
    """POST /admin/tenants/{id}/suspend must publish TENANT_SUSPENDED to Kafka.
    AuditConsumer (not the HTTP handler/service) writes the audit_event row.
    """
    _set_pa_auth(client)

    with patch(
        "routers.tenants.TenantService.suspend",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            "/admin/tenants/tenant-xyz/suspend",
            headers=AUTH_HEADER,
            json={"reason": "Non-payment"},
        )

    assert resp.status_code == 200

    mock_kafka.tenant_event.assert_called_once()
    payload = mock_kafka.tenant_event.call_args[0][0]
    assert payload["event_type"] == "TENANT_SUSPENDED"
    assert payload["tenant_id"] == "tenant-xyz"


# -- Reinstate publishes audit event, never writes audit_event directly ----

@pytest.mark.asyncio
async def test_reinstate_tenant_publishes_audit_event_to_kafka(client, mock_db, mock_kafka):
    """POST /admin/tenants/{id}/reinstate must publish TENANT_REINSTATED to Kafka."""
    _set_pa_auth(client)

    with patch(
        "routers.tenants.TenantService.reinstate",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            "/admin/tenants/tenant-xyz/reinstate",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200

    mock_kafka.tenant_event.assert_called_once()
    payload = mock_kafka.tenant_event.call_args[0][0]
    assert payload["event_type"] == "TENANT_REINSTATED"
    assert payload["tenant_id"] == "tenant-xyz"


@pytest.mark.asyncio
async def test_reinstate_requires_portal_admin(client, mock_db):
    """OA-Admin must not be able to reinstate tenants — PA route only."""
    _set_oa_auth(client)

    resp = await client.post(
        "/admin/tenants/tenant-xyz/reinstate",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reinstate_rejects_non_suspended_tenant_with_409(client, mock_db, mock_kafka):
    """reinstate() raising ValueError must translate to a 409, not a 500."""
    _set_pa_auth(client)

    with patch(
        "routers.tenants.TenantService.reinstate",
        new_callable=AsyncMock,
        side_effect=ValueError("TENANT_NOT_SUSPENDED"),
    ):
        resp = await client.post(
            "/admin/tenants/tenant-xyz/reinstate",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "TENANT_NOT_SUSPENDED"


# -- Response shape --------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tenants_status_query_param_actually_filters(client, mock_db):
    """GET /admin/tenants?status=PENDING must filter by status.

    The query param must bind to the wire name the frontend actually sends
    (`status`) — not an internal-only Python parameter name like
    `status_filter` that FastAPI would silently leave unbound, causing the
    filter to be dropped entirely (OnboardingQueue.tsx has been requesting
    ?status=PENDING and silently getting ALL tenants back).
    """
    _set_pa_auth(client)
    with patch(
        "routers.tenants.TenantService.list_all",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_list_all:
        resp = await client.get("/admin/tenants?status=PENDING", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_list_all.assert_called_once_with("PENDING")


@pytest.mark.asyncio
async def test_tenant_list_returns_wrapped_items_not_bare_array(client, mock_db):
    """GET /admin/tenants must return {"tenants": [...]} — never a bare array."""
    _set_pa_auth(client)
    mock_db.fetch.return_value = [_make_tenant_row()]

    resp = await client.get("/admin/tenants", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    # Must be a dict with a 'tenants' key — not a bare list
    assert isinstance(data, dict), "Response must be an object, not a bare array"
    assert "tenants" in data
    assert isinstance(data["tenants"], list)
