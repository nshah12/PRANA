"""
Tests for routers/checklist.py — the Go-Live Checklist API.

Covers: auth, role enforcement (OA-Operator view-only, OA-Admin write; PA-only
baseline routes), tenant isolation (cannot touch another tenant's item or the
platform baseline via OA-Admin routes), and the wrapped response shapes.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _set_oa_admin_auth(client, tenant_id: str = TENANT_ID) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "22222222-2222-2222-2222-222222222222",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": tenant_id,
        "jti": "oa-admin-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_operator_auth(client, tenant_id: str = TENANT_ID) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "33333333-3333-3333-3333-333333333333",
        "user_type": "oa_user",
        "role": "oa_operator",
        "tenant_id": tenant_id,
        "jti": "oa-operator-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_pa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "44444444-4444-4444-4444-444444444444",
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,
        "jti": "pa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _checklist_row(**overrides):
    row = {
        "item_id": uuid4(), "tenant_id": None, "item_key": "BASELINE_ONE",
        "title": "Baseline Item", "description": "desc", "display_order": 0,
        "is_required": True, "completed_at": None, "completed_by": None, "notes": None,
    }
    row.update(overrides)
    return row


def _platform_item_row(**overrides):
    row = {
        "item_id": uuid4(), "tenant_id": None, "item_key": "BASELINE_ONE",
        "title": "Baseline Item", "description": "desc", "display_order": 0,
        "is_active": True, "is_required": True,
        "created_at": datetime.now(tz=timezone.utc), "updated_at": datetime.now(tz=timezone.utc),
    }
    row.update(overrides)
    return row


# ── Auth / role enforcement ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_checklist_without_token_returns_401(client):
    resp = await client.get("/v1/org/setup-checklist")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_oa_operator_can_view_checklist(client, mock_db):
    _set_oa_operator_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_checklist_row()])
    resp = await client.get("/v1/org/setup-checklist", headers=AUTH_HEADER)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_oa_operator_cannot_complete_item(client, mock_db):
    _set_oa_operator_auth(client)
    resp = await client.post("/v1/org/setup-checklist/BASELINE_ONE/complete", headers=AUTH_HEADER, json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_route_rejects_oa_admin(client, mock_db):
    _set_oa_admin_auth(client)
    resp = await client.get("/admin/setup-checklist", headers=AUTH_HEADER)
    assert resp.status_code == 403


# ── GET /v1/org/setup-checklist ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_checklist_returns_wrapped_shape(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_checklist_row(), _checklist_row(item_key="TWO", tenant_id=None)])
    resp = await client.get("/v1/org/setup-checklist", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
    assert body["total"] == 2
    assert body["items"][0]["item_key"] == "BASELINE_ONE"
    assert body["items"][0]["is_platform_baseline"] is True


@pytest.mark.asyncio
async def test_get_checklist_scopes_query_to_callers_tenant(client, mock_db):
    _set_oa_admin_auth(client, tenant_id="99999999-9999-9999-9999-999999999999")
    mock_db.fetch = AsyncMock(return_value=[])
    await client.get("/v1/org/setup-checklist", headers=AUTH_HEADER)
    call_args = mock_db.fetch.call_args
    assert str(call_args[0][1]) == "99999999-9999-9999-9999-999999999999"


# ── Complete / uncomplete ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oa_admin_completes_item(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"item_id": uuid4()})
    mock_db.execute = AsyncMock()
    resp = await client.post(
        "/v1/org/setup-checklist/baseline_one/complete", headers=AUTH_HEADER, json={"notes": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


@pytest.mark.asyncio
async def test_complete_unknown_item_returns_404(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = await client.post("/v1/org/setup-checklist/NOT_REAL/complete", headers=AUTH_HEADER, json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_oa_admin_uncompletes_item(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"item_id": uuid4()})
    mock_db.execute = AsyncMock(return_value="DELETE 1")
    resp = await client.delete("/v1/org/setup-checklist/BASELINE_ONE/complete", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["completed"] is False


# ── Add / delete tenant item ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oa_admin_adds_tenant_item(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow = AsyncMock(side_effect=[None, _platform_item_row(tenant_id=TENANT_ID, item_key="MY_ITEM", title="My Item")])
    resp = await client.post(
        "/v1/org/setup-checklist", headers=AUTH_HEADER,
        json={"item_key": "my_item", "title": "My Item", "is_required": True},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["item_key"] == "MY_ITEM"


@pytest.mark.asyncio
async def test_oa_admin_add_item_conflict_returns_409(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"item_id": uuid4()})
    resp = await client.post(
        "/v1/org/setup-checklist", headers=AUTH_HEADER,
        json={"item_key": "DUPLICATE", "title": "Dup"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_oa_operator_cannot_add_tenant_item(client, mock_db):
    _set_oa_operator_auth(client)
    resp = await client.post(
        "/v1/org/setup-checklist", headers=AUTH_HEADER,
        json={"item_key": "X", "title": "X"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_oa_admin_deletes_own_item(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.execute = AsyncMock(return_value="DELETE 1")
    resp = await client.delete("/v1/org/setup-checklist/MY_ITEM", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_delete_nonexistent_tenant_item_returns_404(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.execute = AsyncMock(return_value="DELETE 0")
    resp = await client.delete("/v1/org/setup-checklist/BASELINE_ONE", headers=AUTH_HEADER)
    assert resp.status_code == 404


# ── PA — platform baseline management ────────────────────────────────────────

@pytest.mark.asyncio
async def test_pa_lists_platform_items(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_platform_item_row()])
    resp = await client.get("/admin/setup-checklist", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["tenant_id"] is None


@pytest.mark.asyncio
async def test_pa_adds_platform_item(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(side_effect=[None, _platform_item_row(item_key="NEW_BASELINE")])
    resp = await client.post(
        "/admin/setup-checklist", headers=AUTH_HEADER,
        json={"item_key": "new_baseline", "title": "New Baseline", "is_required": True},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["item_key"] == "NEW_BASELINE"


@pytest.mark.asyncio
async def test_pa_add_platform_item_conflict_returns_409(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value={"item_id": uuid4()})
    resp = await client.post(
        "/admin/setup-checklist", headers=AUTH_HEADER,
        json={"item_key": "DUPLICATE", "title": "Dup"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_pa_updates_platform_item(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value=_platform_item_row(is_active=False))
    resp = await client.patch(
        f"/admin/setup-checklist/{uuid4()}", headers=AUTH_HEADER,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["is_active"] is False


@pytest.mark.asyncio
async def test_pa_update_unknown_item_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = await client.patch(
        f"/admin/setup-checklist/{uuid4()}", headers=AUTH_HEADER,
        json={"title": "X"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_oa_admin_cannot_reach_pa_update_route(client, mock_db):
    _set_oa_admin_auth(client)
    resp = await client.patch(
        f"/admin/setup-checklist/{uuid4()}", headers=AUTH_HEADER,
        json={"title": "X"},
    )
    assert resp.status_code == 403
