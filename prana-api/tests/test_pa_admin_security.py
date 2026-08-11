"""
Tests for routers/pa_admin_security.py — security, audit & incidents.
Split 2026-08-10 out of test_pa_admin.py (see that file's docstring). Covers:
application errors (4th incident track).
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
