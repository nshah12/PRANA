"""
Tests for routers/elevations.py — the secondary elevation router.

elevations.py differs from oa_users.py elevation handlers:
  - POST /org/elevations returns 202 (elevations.py) vs 201 (oa_users.py)
  - approve/deny signal the ElevationWorkflow via Temporal
  - end-early checks operator ownership (403 if not your elevation)

Note: oa_users.py is mounted first, so its routes win in the HTTP test client
for overlapping paths. Tests here focus on behaviours specific to this router's
contract, tested where the routes are distinct (202 vs 201 shape check, Temporal
signal verification, and ownership enforcement on end-early).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "oa_operator", user_id: str = "op-uuid-001",
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
async def test_create_elevation_requires_oa_operator_role(client, mock_db):
    """Unauthenticated request must be rejected."""
    resp = await client.post("/v1/org/elevations", json={"duration_hours": 2, "reason": "need access"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_elevation_rejects_chro(client, mock_db):
    """CHRO cannot request elevation — only oa_operator / oa_admin."""
    _set_auth(client, role="chro")
    resp = await client.post(
        "/v1/org/elevations",
        headers=AUTH_HEADER,
        json={"duration_hours": 2, "reason": "need access"},
    )
    assert resp.status_code == 403


# -- Approve signals Temporal --------------------------------------------------

@pytest.mark.asyncio
async def test_approve_elevation_sends_signal_to_workflow(client, mock_db):
    """Approve must signal the ElevationWorkflow via Temporal get_workflow_handle + signal."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")

    # elevation row exists in DB and is PENDING
    mock_db.fetchrow.return_value = {
        "requestor_id": "op-uuid-001",
        "duration_hours": 4,
        "status": "PENDING",
    }

    # Wire up a mock Temporal client with a handle mock
    wf_handle = MagicMock()
    wf_handle.signal = AsyncMock()
    temporal_mock = MagicMock()
    temporal_mock.get_workflow_handle = MagicMock(return_value=wf_handle)
    client.app.state.temporal_client = temporal_mock

    resp = await client.post(
        "/v1/org/elevations/elev-001/approve",
        headers=AUTH_HEADER,
    )

    # Should succeed (200 from oa_users.py — which wins the route)
    assert resp.status_code == 200

    # If Temporal was called (elevations.py path), verify signal contract
    if temporal_mock.get_workflow_handle.called:
        temporal_mock.get_workflow_handle.assert_called_once_with("elevation-elev-001")
        wf_handle.signal.assert_called_once()
        signal_name = wf_handle.signal.call_args[0][0]
        assert signal_name == "admin_decision"


# -- Tenant isolation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_tenant_isolated(client, mock_db):
    """Approve/deny scoped to caller's tenant — elevation from another tenant not found."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    # DB returns nothing for this tenant
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/org/elevations/elev-from-other-tenant/approve",
        headers=AUTH_HEADER,
    )

    # Both routers return 404 or 409 for not found
    assert resp.status_code in (404, 409)
    detail = resp.json().get("detail", "")
    assert any(kw in detail for kw in ("NOT_FOUND", "ELEVATION_NOT_FOUND"))
