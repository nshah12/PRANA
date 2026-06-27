"""
RED tests for PA hrms_definitions router.

Endpoints tested:
  GET  /v1/admin/hrms/definitions          — list all connector definitions
  GET  /v1/admin/hrms/definitions/{key}    — get single definition by connector_key
  POST /v1/admin/hrms/definitions          — create new connector type
  PATCH /v1/admin/hrms/definitions/{id}/activate   — enable
  PATCH /v1/admin/hrms/definitions/{id}/deactivate — disable

PA-only. Any other role → 403.
"""
import pytest
import pytest_asyncio
from uuid import uuid4

CONN_DEF_ID = str(uuid4())

DARWINBOX_ROW = {
    "connector_definition_id": CONN_DEF_ID,
    "connector_key":           "darwinbox",
    "display_name":            "Darwinbox",
    "auth_method":             "OAUTH2",
    "supported_modes":         ["PULL", "WEBHOOK"],
    "canonical_field_schema":  '{"employee_id":"employee_id"}',
    "docs_url":                "https://developers.darwinbox.com/",
    "is_active":               True,
    "created_at":              None,
    "updated_at":              None,
}


def _pa_headers(client):
    """Inject PA JWT and return auth headers."""
    from unittest.mock import AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       "f0000000-0000-0000-0000-000000000001",
        "user_type": "portal_admin",
        "jti":       "pa-session-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.pa.jwt"}


def _oa_headers(client):
    """OA user — must be denied PA-only endpoints."""
    from unittest.mock import AsyncMock
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       "a0000000-0000-0000-0000-000000000002",
        "user_type": "oa_user",
        "role":      "OA-Admin",
        "tenant_id": "b0000000-0000-0000-0000-000000000001",
        "jti":       "oa-session-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.oa.jwt"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_definitions_unauthenticated(client):
    r = await client.get("/v1/admin/hrms/definitions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_definitions_oa_user_forbidden(client):
    r = await client.get("/v1/admin/hrms/definitions", headers=_oa_headers(client))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_definition_unauthenticated(client):
    r = await client.post("/v1/admin/hrms/definitions", json={})
    assert r.status_code == 401


# ── List ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_definitions_returns_items(client):
    from unittest.mock import MagicMock
    row = MagicMock()
    row.__getitem__ = lambda s, k: DARWINBOX_ROW[k]
    client.app.state.db_pool.acquire().__aenter__.return_value.fetch = \
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=[row])

    r = await client.get("/v1/admin/hrms/definitions", headers=_pa_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


# ── Get single ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_definition_by_key(client):
    from unittest.mock import MagicMock
    row = MagicMock()
    row.__getitem__ = lambda s, k: DARWINBOX_ROW[k]
    client.app.state.db_pool.acquire().__aenter__.return_value.fetchrow = \
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=row)

    r = await client.get("/v1/admin/hrms/definitions/darwinbox", headers=_pa_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["connector_key"] == "darwinbox"


@pytest.mark.asyncio
async def test_get_definition_not_found(client):
    client.app.state.db_pool.acquire().__aenter__.return_value.fetchrow = \
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=None)

    r = await client.get("/v1/admin/hrms/definitions/nope", headers=_pa_headers(client))
    assert r.status_code == 404


# ── Create ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_definition_happy_path(client):
    from unittest.mock import AsyncMock
    new_id = str(uuid4())
    client.app.state.db_pool.acquire().__aenter__.return_value.fetchval = \
        AsyncMock(return_value=new_id)

    payload = {
        "connector_key":           "greythr",
        "display_name":            "Greythr",
        "auth_method":             "API_KEY",
        "supported_modes":         ["PULL"],
        "canonical_field_schema":  {"employee_id": "empId"},
    }
    r = await client.post("/v1/admin/hrms/definitions", json=payload, headers=_pa_headers(client))
    assert r.status_code == 201
    body = r.json()
    assert "connector_definition_id" in body


@pytest.mark.asyncio
async def test_create_definition_invalid_auth_method(client):
    payload = {
        "connector_key":   "bad",
        "display_name":    "Bad",
        "auth_method":     "BASIC",
        "supported_modes": ["PULL"],
        "canonical_field_schema": {},
    }
    r = await client.post("/v1/admin/hrms/definitions", json=payload, headers=_pa_headers(client))
    assert r.status_code == 422


# ── Activate / Deactivate ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_definition(client):
    from unittest.mock import AsyncMock
    client.app.state.db_pool.acquire().__aenter__.return_value.execute = AsyncMock()

    r = await client.patch(
        f"/v1/admin/hrms/definitions/{CONN_DEF_ID}/deactivate",
        headers=_pa_headers(client),
    )
    assert r.status_code == 200
    assert r.json().get("status") == "deactivated"


@pytest.mark.asyncio
async def test_activate_definition(client):
    from unittest.mock import AsyncMock
    client.app.state.db_pool.acquire().__aenter__.return_value.execute = AsyncMock()

    r = await client.patch(
        f"/v1/admin/hrms/definitions/{CONN_DEF_ID}/activate",
        headers=_pa_headers(client),
    )
    assert r.status_code == 200
    assert r.json().get("status") == "activated"
