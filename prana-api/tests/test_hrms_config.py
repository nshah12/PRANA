"""
RED tests for tenant hrms_config router.

Endpoints:
  GET    /v1/hrms/config                             — list tenant's connectors
  GET    /v1/hrms/config/{connector_id}              — get one
  POST   /v1/hrms/config                             — create (OA-Admin only)
  PATCH  /v1/hrms/config/{connector_id}/field-mapping
  PATCH  /v1/hrms/config/{connector_id}/pause
  PATCH  /v1/hrms/config/{connector_id}/resume

Rules verified:
- Unauthenticated → 401
- Employee → 403
- OA-Operator (non-Admin) create → 403
- tenant_id from JWT only — never from request body
- Credentials never appear in response
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

TENANT_ID    = "b0000000-0000-0000-0000-000000000001"
CONN_DEF_ID  = str(uuid4())
CONNECTOR_ID = str(uuid4())

CONFIG_ROW = {
    "connector_id":            CONNECTOR_ID,
    "tenant_id":               TENANT_ID,
    "connector_definition_id": CONN_DEF_ID,
    "display_name":            "Darwinbox – NPCI",
    "integration_mode":        "PULL",
    "last_pulled_at":          None,
    "pull_schedule":           None,
    "status":                  "ACTIVE",
    "field_mapping":           "{}",
    "connector_key":           "darwinbox",
    "definition_name":         "Darwinbox",
    "auth_method":             "OAUTH2",
    "supported_modes":         ["PULL", "WEBHOOK"],
}


def _oa_admin_headers(client):
    from unittest.mock import AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       "a0000000-0000-0000-0000-000000000001",
        "user_type": "oa_user",
        "role":      "OA-Admin",
        "tenant_id": TENANT_ID,
        "jti":       "oa-admin-session-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.oa.admin.jwt"}


def _oa_operator_headers(client):
    from unittest.mock import AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       "a0000000-0000-0000-0000-000000000003",
        "user_type": "oa_user",
        "role":      "OA-Operator",
        "tenant_id": TENANT_ID,
        "jti":       "oa-op-session-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.oa.operator.jwt"}


def _employee_headers(client):
    from unittest.mock import AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       "a0000000-0000-0000-0000-000000000002",
        "user_type": "employee",
        "jti":       "emp-session-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.employee.jwt"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_unauthenticated(client):
    r = await client.get("/v1/hrms/config")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_employee_forbidden(client):
    r = await client.get("/v1/hrms/config", headers=_employee_headers(client))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_config_unauthenticated(client):
    r = await client.post("/v1/hrms/config", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_config_operator_forbidden(client):
    """OA-Operator cannot create connector configs — OA-Admin only."""
    payload = {
        "connector_definition_id": CONN_DEF_ID,
        "display_name": "Darwinbox – Acme",
        "integration_mode": "PULL",
        "credentials": {"client_id": "x", "client_secret": "y"},
    }
    r = await client.post("/v1/hrms/config", json=payload, headers=_oa_operator_headers(client))
    assert r.status_code == 403


# ── List ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_returns_items_shape(client):
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONFIG_ROW[k]
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetch = AsyncMock(return_value=[row])

    r = await client.get("/v1/hrms/config", headers=_oa_admin_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_no_credentials_in_response(client):
    """enc_credentials / raw creds must never appear in API response."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONFIG_ROW.get(k)
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetch = AsyncMock(return_value=[row])

    r = await client.get("/v1/hrms/config", headers=_oa_admin_headers(client))
    assert r.status_code == 200
    body_text = r.text
    assert "enc_credentials" not in body_text
    assert "client_secret" not in body_text


# ── Get single ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_not_found(client):
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetchrow = AsyncMock(return_value=None)

    r = await client.get(f"/v1/hrms/config/{CONNECTOR_ID}", headers=_oa_admin_headers(client))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_config_found(client):
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONFIG_ROW[k]
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetchrow = AsyncMock(return_value=row)

    r = await client.get(f"/v1/hrms/config/{CONNECTOR_ID}", headers=_oa_admin_headers(client))
    assert r.status_code == 200
    assert r.json()["connector_key"] == "darwinbox"


# ── Create ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_config_happy_path(client):
    new_id = str(uuid4())
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetchval = AsyncMock(side_effect=["arn:aws:kms:ap-south-1:123:key/test", new_id])

    # kms_service must encrypt
    client.app.state.kms_service.encrypt = MagicMock(return_value=b"encrypted")

    payload = {
        "connector_definition_id": CONN_DEF_ID,
        "display_name": "Darwinbox – NPCI",
        "integration_mode": "PULL",
        "credentials": {"client_id": "abc", "client_secret": "secret"},
    }
    r = await client.post("/v1/hrms/config", json=payload, headers=_oa_admin_headers(client))
    assert r.status_code == 201
    body = r.json()
    assert "connector_id" in body
    # raw secret must NOT be in response
    assert "secret" not in r.text


# ── Field mapping ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_field_mapping(client):
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.execute = AsyncMock()

    r = await client.patch(
        f"/v1/hrms/config/{CONNECTOR_ID}/field-mapping",
        json={"field_mapping": {"employee_id": "emp_code"}},
        headers=_oa_admin_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "updated"


# ── Pause / Resume ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pause_connector(client):
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.execute = AsyncMock()

    r = await client.patch(
        f"/v1/hrms/config/{CONNECTOR_ID}/pause",
        headers=_oa_admin_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_connector(client):
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.execute = AsyncMock()

    r = await client.patch(
        f"/v1/hrms/config/{CONNECTOR_ID}/resume",
        headers=_oa_admin_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_id_from_jwt_not_body(client):
    """Tenant ID must come from JWT — the payload should not accept tenant_id."""
    db = client.app.state.db_pool.acquire().__aenter__.return_value
    db.fetchval = AsyncMock(side_effect=["arn:aws:kms:ap-south-1:123:key/test", str(uuid4())])
    client.app.state.kms_service.encrypt = MagicMock(return_value=b"enc")

    payload = {
        "connector_definition_id": CONN_DEF_ID,
        "display_name": "Darwinbox – NPCI",
        "integration_mode": "PULL",
        "credentials": {"client_id": "x"},
        "tenant_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",  # must be ignored
    }
    r = await client.post("/v1/hrms/config", json=payload, headers=_oa_admin_headers(client))
    # Should succeed (201) using JWT tenant_id, ignoring the body tenant_id
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        # The stored tenant_id was from JWT (TENANT_ID), never from body
        assert "ffffffff" not in r.text
