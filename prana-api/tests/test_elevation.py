"""
Tests for the elevation request / approve / deny / end-early flows.

Covers:
  - Request blocked if PENDING or ACTIVE already exists
  - Duration must be 2, 4, or 8 hours
  - Only OA-Operator who made the request can end-early
  - Approve sends Temporal signal
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _oa_header(role="oa_operator", user_id="op-uuid-001", tenant_id="tenant-001"):
    """Returns a mock JWT claims dict used by require_oa dependency."""
    return {"sub": user_id, "role": role, "tenant_id": tenant_id}


@pytest.mark.asyncio
async def test_elevation_blocked_if_pending_exists(client, mock_db):
    """Cannot request elevation if one is already PENDING for this operator."""
    # Simulate an existing PENDING elevation
    mock_db.fetchrow.return_value = {"elevation_id": "existing-elev-001"}

    with patch("routers.elevations.require_oa", return_value=MagicMock(
        user_id="op-uuid-001", tenant_id="tenant-001", role="oa_operator"
    )):
        resp = await client.post("/org/elevations", json={
            "reason": "Need access to resolve exception",
            "duration_hours": 2,
        })

    assert resp.status_code == 409
    assert "ALREADY_EXISTS" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_elevation_invalid_duration(client, mock_db):
    """Duration must be 2, 4, or 8 — other values should fail validation."""
    mock_db.fetchrow.return_value = None  # no existing elevation

    with patch("routers.elevations.require_oa", return_value=MagicMock(
        user_id="op-uuid-001", tenant_id="tenant-001", role="oa_operator"
    )):
        resp = await client.post("/org/elevations", json={
            "reason": "Valid reason",
            "duration_hours": 5,   # invalid — not 2/4/8
        })

    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_end_early_blocked_for_wrong_operator(client, mock_db):
    """Only the operator who requested the elevation can end it early."""
    mock_db.fetchrow.return_value = {
        "elevation_id": "elev-001",
        "requestor_id": "op-uuid-999",   # different operator
        "status": "ACTIVE",
    }

    with patch("routers.elevations.require_oa", return_value=MagicMock(
        user_id="op-uuid-001",  # this is not the requestor
        tenant_id="tenant-001",
        role="oa_operator",
    )):
        resp = await client.post("/org/elevations/elev-001/end-early")

    assert resp.status_code == 403
    assert "NOT_YOUR_ELEVATION" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_approve_sends_temporal_signal(client, mock_db):
    """Approve must signal the ElevationWorkflow via Temporal, not do the work inline."""
    mock_db.fetchrow.return_value = {
        "elevation_id": "elev-001",
        "requestor_id": "op-uuid-001",
        "status": "PENDING",
        "tenant_id": "tenant-001",
    }

    temporal_mock = MagicMock()
    handle_mock = MagicMock()
    handle_mock.signal = AsyncMock()
    temporal_mock.get_workflow_handle = MagicMock(return_value=handle_mock)
    client.app.state.temporal_client = temporal_mock

    with patch("routers.elevations.require_oa", return_value=MagicMock(
        user_id="admin-uuid-001", tenant_id="tenant-001", role="oa_admin"
    )):
        resp = await client.post("/org/elevations/elev-001/approve")

    # Must have called Temporal signal
    handle_mock.signal.assert_called_once()
    signal_name = handle_mock.signal.call_args[0][0]
    assert signal_name == "admin_decision"
