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
