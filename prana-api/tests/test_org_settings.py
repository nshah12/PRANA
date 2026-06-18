"""
Tests for routers/org_settings.py — tenant settings and profile management.

Covers:
  - Auth guard: PATCH /settings requires oa_admin (oa_operator cannot update)
  - Tenant scoping: settings update uses tenant_id from JWT
  - Valid channel validation: only personal_email / work_email / sms accepted
  - GET /settings accessible to any OA role
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "oa_admin", user_id: str = "admin-uuid-001",
              tenant_id: str = "tenant-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


# -- Auth guard ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_settings_requires_oa_admin(client, mock_db):
    """oa_operator cannot update settings — requires oa_admin."""
    _set_auth(client, role="oa_operator")
    resp = await client.patch(
        "/v1/org/settings",
        headers=AUTH_HEADER,
        json={"employee_activation_channels": "personal_email"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_settings_unauthenticated_rejected(client, mock_db):
    """Unauthenticated PATCH must be rejected."""
    resp = await client.patch(
        "/v1/org/settings",
        json={"employee_activation_channels": "personal_email"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_settings_accessible_to_oa_operator(client, mock_db):
    """GET /settings is accessible to any OA role including oa_operator."""
    _set_auth(client, role="oa_operator")
    mock_db.fetchrow.return_value = {
        "tenant_id": "tenant-001",
        "tenant_name": "Acme Corp",
        "domain": "acme.com",
        "status": "ACTIVE",
        "home_region": "ap-south-1",
        "self_upload_policy": "ALLOWED",
        "employee_activation_channels": "personal_email",
    }

    resp = await client.get("/v1/org/settings", headers=AUTH_HEADER)
    assert resp.status_code == 200


# -- Tenant scoping ------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_update_scoped_to_caller_tenant(client, mock_db):
    """Settings update must use tenant_id from JWT — not a body parameter."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-xyz")
    mock_db.fetchval.return_value = None  # no BFSI policy
    mock_db.execute.return_value = None

    resp = await client.patch(
        "/v1/org/settings",
        headers=AUTH_HEADER,
        json={"employee_activation_channels": "personal_email"},
    )

    assert resp.status_code == 200

    # The INSERT/UPDATE must have been called with the JWT's tenant_id
    upsert_args = str(mock_db.execute.call_args)
    assert "tenant-xyz" in upsert_args


# -- Channel validation -------------------------------------------------------

@pytest.mark.asyncio
async def test_update_settings_invalid_channel_rejected(client, mock_db):
    """Invalid channel value must return 422 INVALID_CHANNELS."""
    _set_auth(client, role="oa_admin")
    mock_db.fetchval.return_value = None

    resp = await client.patch(
        "/v1/org/settings",
        headers=AUTH_HEADER,
        json={"employee_activation_channels": "telegram"},  # not a valid channel
    )

    assert resp.status_code == 422
    assert "INVALID_CHANNELS" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_update_settings_happy_path(client, mock_db):
    """oa_admin can update activation channels — returns 200 with message."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchval.return_value = None  # no BFSI policy
    mock_db.execute.return_value = None

    resp = await client.patch(
        "/v1/org/settings",
        headers=AUTH_HEADER,
        json={"employee_activation_channels": "personal_email,sms"},
    )

    assert resp.status_code == 200
    assert "message" in resp.json()
