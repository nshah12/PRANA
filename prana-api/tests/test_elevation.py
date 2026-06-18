"""
Tests for the elevation request / approve / deny / end-early flows.

The active implementation is in routers/oa_users.py + services/elevation_service.py.
(routers/elevations.py is a second router mounted later — oa_users.py wins on route conflicts.)

Covers:
  - Auth guard: requires oa_operator / oa_admin role
  - Request blocked if PENDING already exists
  - Duration must be 2, 4, or 8 hours
  - Happy path: request returns elevation_id + PENDING
  - Approve: updates status to ACTIVE
  - Deny: updates status to DENIED
  - Tenant isolation: approve/deny scoped to tenant
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
async def test_elevations_requires_auth(client, mock_db):
    """Unauthenticated requests must be rejected."""
    resp = await client.post("/v1/org/elevations", json={
        "reason": "need access", "duration_hours": 2,
    })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_elevations_rejects_chro_role(client, mock_db):
    """CHRO cannot request elevations."""
    _set_auth(client, role="chro")
    resp = await client.post("/v1/org/elevations", headers=AUTH_HEADER, json={
        "reason": "need access", "duration_hours": 2,
    })
    assert resp.status_code == 403


# -- Request flow --------------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_blocked_if_pending_exists(client, mock_db):
    """Cannot request elevation if one is already PENDING."""
    _set_auth(client)
    # fetchrow returns an existing pending row
    mock_db.fetchrow.return_value = {"elevation_id": "existing-elev-001"}

    resp = await client.post("/v1/org/elevations", headers=AUTH_HEADER, json={
        "reason": "Need access to resolve exception",
        "duration_hours": 2,
    })

    assert resp.status_code == 409
    assert "PENDING_REQUEST_EXISTS" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_elevation_invalid_duration(client, mock_db):
    """Duration must be 2, 4, or 8 — other values must fail with 409."""
    _set_auth(client)
    mock_db.fetchrow.return_value = None  # no existing elevation

    resp = await client.post("/v1/org/elevations", headers=AUTH_HEADER, json={
        "reason": "Valid reason",
        "duration_hours": 5,   # invalid
    })

    # ElevationService raises ValueError("INVALID_DURATION") -> router -> 409
    assert resp.status_code == 409
    assert "INVALID_DURATION" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_elevation_valid_durations_accepted(client, mock_db):
    """Durations 2, 4, 8 must all be accepted."""
    for hours in (2, 4, 8):
        _set_auth(client)
        mock_db.fetchrow.return_value = None  # no existing elevation

        resp = await client.post("/v1/org/elevations", headers=AUTH_HEADER, json={
            "reason": "Valid reason",
            "duration_hours": hours,
        })
        assert resp.status_code == 201, f"Expected 201 for duration_hours={hours}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_elevation_request_returns_pending_status(client, mock_db):
    """Successful request returns elevation_id + PENDING status."""
    _set_auth(client)
    mock_db.fetchrow.return_value = None  # no existing pending

    resp = await client.post("/v1/org/elevations", headers=AUTH_HEADER, json={
        "reason": "Emergency access",
        "duration_hours": 4,
    })

    assert resp.status_code == 201
    data = resp.json()
    assert "elevation_id" in data
    assert data["status"] == "PENDING"


# -- Approve -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_elevation_happy_path(client, mock_db):
    """Admin can approve a PENDING elevation - returns ACTIVE status."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")
    mock_db.fetchrow.return_value = {
        "requestor_id": "op-uuid-001",   # different from approver
        "duration_hours": 4,
        "status": "PENDING",
    }

    resp = await client.post(
        "/v1/org/elevations/elev-001/approve",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "elevation_id" in data
    assert data["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_approve_rejects_non_admin(client, mock_db):
    """Only oa_admin can approve — oa_operator must be rejected."""
    _set_auth(client, role="oa_operator")

    resp = await client.post(
        "/v1/org/elevations/elev-001/approve",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_returns_409_if_not_found(client, mock_db):
    """Approve on a non-existent elevation must return 409 (service raises ValueError)."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/org/elevations/does-not-exist/approve",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 409


# -- Deny ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deny_elevation_happy_path(client, mock_db):
    """Admin can deny a PENDING elevation."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")

    resp = await client.post(
        "/v1/org/elevations/elev-001/deny",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    assert resp.json().get("message") == "Denied"


@pytest.mark.asyncio
async def test_deny_rejects_non_admin(client, mock_db):
    """Only oa_admin can deny — oa_operator must be rejected."""
    _set_auth(client, role="oa_operator")

    resp = await client.post(
        "/v1/org/elevations/elev-001/deny",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 403


# -- End-early ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_end_early_happy_path(client, mock_db):
    """Operator can end their own active elevation early."""
    _set_auth(client, role="oa_operator", user_id="op-uuid-001")

    resp = await client.post(
        "/v1/org/elevations/elev-001/end-early",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    assert resp.json().get("message") == "Elevation ended"


# -- Tenant isolation ---------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_tenant_isolation(client, mock_db):
    """Approve scoped by tenant_id — elevation from another tenant returns 409."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    # DB returns no row for this tenant_id combination
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/org/elevations/elev-from-other-tenant/approve",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 409
    assert "NOT_FOUND" in resp.json().get("detail", "")
