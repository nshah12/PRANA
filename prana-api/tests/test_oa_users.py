"""
Tests for routers/oa_users.py — OA user CRUD (create, deactivate, change-role, unlock).

Covers:
  - Auth guard: requires oa_admin for user creation
  - Tenant scoping: tenant_id from JWT, never from request body
  - Welcome email dispatched via Kafka (prana.notifications), not in HTTP path directly
  - Email domain validation enforced
"""
from unittest.mock import AsyncMock, MagicMock, call

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
async def test_create_oa_user_requires_oa_admin(client, mock_db):
    """Unauthenticated requests must be rejected."""
    resp = await client.post("/v1/org/users", json={"email": "op@acme.com", "role": "oa_operator"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_oa_user_rejects_oa_operator_role(client, mock_db):
    """oa_operator cannot create users — only oa_admin."""
    _set_auth(client, role="oa_operator")
    resp = await client.post(
        "/v1/org/users",
        headers=AUTH_HEADER,
        json={"email": "newop@acme.com", "role": "oa_operator"},
    )
    assert resp.status_code == 403


# -- Tenant scoping ------------------------------------------------------------

@pytest.mark.asyncio
async def test_oa_user_creation_scoped_to_caller_tenant(client, mock_db):
    """tenant_id must come from JWT — new user placed in caller's tenant, not a body field."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")

    # Domain check: tenant domain = acme.com
    mock_db.fetchrow.return_value = {"domain": "acme.com"}
    mock_db.execute.return_value = None

    resp = await client.post(
        "/v1/org/users",
        headers=AUTH_HEADER,
        json={"email": "newop@acme.com", "role": "oa_operator"},
    )

    assert resp.status_code == 201

    # Verify the INSERT used tenant-001 from JWT, not any body value
    insert_call_args = str(mock_db.execute.call_args_list)
    assert "tenant-001" in insert_call_args


@pytest.mark.asyncio
async def test_oa_user_email_domain_mismatch_rejected(client, mock_db):
    """Email must match the tenant's registered domain — mismatch returns 422."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"domain": "acme.com"}

    resp = await client.post(
        "/v1/org/users",
        headers=AUTH_HEADER,
        json={"email": "newop@competitor.com", "role": "oa_operator"},
    )

    assert resp.status_code == 422
    assert "EMAIL_DOMAIN_MISMATCH" in resp.json().get("detail", "")


# -- Kafka welcome email -------------------------------------------------------

@pytest.mark.asyncio
async def test_oa_user_welcome_email_dispatched_via_kafka(client, mock_db, mock_kafka):
    """On successful OA user creation, a welcome email event must be published to Kafka.
    The NotifConsumer dispatches the actual email — not the HTTP handler directly.
    """
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"domain": "acme.com"}
    mock_db.execute.return_value = None

    resp = await client.post(
        "/v1/org/users",
        headers=AUTH_HEADER,
        json={"email": "newop@acme.com", "role": "oa_operator"},
    )

    assert resp.status_code == 201

    # Kafka publish must have been called with OA_USER_CREATED
    mock_kafka.oa_user_event.assert_called_once()
    payload = mock_kafka.oa_user_event.call_args[0][0]
    assert payload["event_type"] == "OA_USER_CREATED"
    assert payload["email"] == "newop@acme.com"
    assert payload["tenant_id"] == "tenant-001"


@pytest.mark.asyncio
async def test_create_oa_user_response_shape(client, mock_db, mock_kafka):
    """Successful creation returns oa_user_id and a confirmation message."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"domain": "acme.com"}
    mock_db.execute.return_value = None

    resp = await client.post(
        "/v1/org/users",
        headers=AUTH_HEADER,
        json={"email": "newop@acme.com", "role": "oa_operator"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert "oa_user_id" in data
    assert "message" in data
