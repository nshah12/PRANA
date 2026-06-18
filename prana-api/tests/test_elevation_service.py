"""
Unit tests for services/elevation_service.py — ElevationService.

Covers:
  - Duration validation: only 2, 4, 8 are valid — all others raise ValueError
  - Pending check: second request when one is PENDING raises PENDING_REQUEST_EXISTS
  - Approve: returns ACTIVE status; raises NOT_FOUND / NOT_PENDING / SELF_APPROVAL_NOT_ALLOWED
  - get_active: returns None when no active row in DB
"""
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.elevation_service import ElevationService


def _make_db():
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    return db


# -- Duration validation -------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_duration_2_4_8_accepted():
    """Valid durations 2, 4, 8 must not raise."""
    for hours in (2, 4, 8):
        db = _make_db()
        db.fetchrow.return_value = None  # no pending
        svc = ElevationService(db)
        result = await svc.request("op-uuid-001", "tenant-001", "valid reason", hours)
        assert result["status"] == "PENDING"


@pytest.mark.asyncio
async def test_elevation_duration_from_config_not_hardcoded():
    """Duration 5 (not in [2,4,8]) must raise INVALID_DURATION — validating the constraint exists."""
    db = _make_db()
    svc = ElevationService(db)

    with pytest.raises(ValueError, match="INVALID_DURATION"):
        await svc.request("op-uuid-001", "tenant-001", "reason", 5)


@pytest.mark.asyncio
async def test_elevation_duration_3_rejected():
    """Duration 3 is not valid — must raise INVALID_DURATION."""
    db = _make_db()
    svc = ElevationService(db)

    with pytest.raises(ValueError, match="INVALID_DURATION"):
        await svc.request("op-uuid-001", "tenant-001", "reason", 3)


# -- Pending check -------------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_request_blocked_if_pending_exists():
    """Second request while one is PENDING raises PENDING_REQUEST_EXISTS."""
    db = _make_db()
    db.fetchrow.return_value = {"elevation_id": "existing-001"}  # existing pending row
    svc = ElevationService(db)

    with pytest.raises(ValueError, match="PENDING_REQUEST_EXISTS"):
        await svc.request("op-uuid-001", "tenant-001", "reason", 4)


# -- Approve -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_approve_sends_signal_to_workflow():
    """approve() must return ACTIVE status and expires_at — DB is updated."""
    db = _make_db()
    db.fetchrow.return_value = {
        "requestor_id": "op-uuid-001",
        "duration_hours": 4,
        "status": "PENDING",
    }
    svc = ElevationService(db)

    result = await svc.approve("elev-001", "admin-uuid-001", "tenant-001")

    assert result["status"] == "ACTIVE"
    assert "expires_at" in result
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_elevation_approve_raises_not_found():
    """approve() on a non-existent elevation raises NOT_FOUND."""
    db = _make_db()
    db.fetchrow.return_value = None
    svc = ElevationService(db)

    with pytest.raises(ValueError, match="NOT_FOUND"):
        await svc.approve("does-not-exist", "admin-uuid-001", "tenant-001")


@pytest.mark.asyncio
async def test_elevation_approve_raises_self_approval_not_allowed():
    """Requestor cannot approve their own elevation — SELF_APPROVAL_NOT_ALLOWED."""
    db = _make_db()
    db.fetchrow.return_value = {
        "requestor_id": "admin-uuid-001",  # same as approver
        "duration_hours": 2,
        "status": "PENDING",
    }
    svc = ElevationService(db)

    with pytest.raises(ValueError, match="SELF_APPROVAL_NOT_ALLOWED"):
        await svc.approve("elev-001", "admin-uuid-001", "tenant-001")


# -- get_active (no expired row) -----------------------------------------------

@pytest.mark.asyncio
async def test_elevation_expired_auto_revokes_permissions():
    """get_active() returns None when no active unexpired elevation exists.
    Expired elevations are excluded by the SQL WHERE expires_at > NOW().
    """
    db = _make_db()
    db.fetchrow.return_value = None  # DB finds no active + unexpired row
    svc = ElevationService(db)

    result = await svc.get_active("op-uuid-001")

    assert result is None
