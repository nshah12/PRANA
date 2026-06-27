"""
Tests for routers/sessions.py — session management.

Covers:
  - Auth guard: force-revoke requires ciso or oa_admin
  - Kafka audit event published on force-revoke (SESSION_FORCE_REVOKED)
  - Tenant isolation: session from another tenant returns 404
  - Already-revoked session returns 409
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "ciso", user_id: str = "ciso-uuid-001",
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


def _make_session_row(revoked: bool = False, tenant_id: str = "tenant-001"):
    return {
        "session_id": "sess-uuid-001",
        "user_id": "emp-uuid-001",
        "revoked": revoked,
        "tenant_id": tenant_id,
    }


# -- Auth guard ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_revoke_session_requires_ciso_or_oa_admin(client, mock_db):
    """Unauthenticated force-revoke must be rejected."""
    resp = await client.post("/auth/sessions/sess-uuid-001/revoke")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_force_revoke_rejects_oa_operator(client, mock_db):
    """oa_operator cannot force-revoke sessions — only ciso / oa_admin."""
    _set_auth(client, role="oa_operator")
    resp = await client.post("/auth/sessions/sess-uuid-001/revoke", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_force_revoke_rejects_chro(client, mock_db):
    """CHRO cannot force-revoke sessions."""
    _set_auth(client, role="chro")
    resp = await client.post("/auth/sessions/sess-uuid-001/revoke", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_force_revoke_allowed_for_oa_admin(client, mock_db, mock_kafka):
    """oa_admin can force-revoke sessions."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")
    mock_db.fetchrow.return_value = _make_session_row()
    mock_db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    mock_db.execute = AsyncMock(return_value=None)
    jwt = client.app.state.jwt_service
    jwt.revoke = AsyncMock()

    resp = await client.post("/auth/sessions/sess-uuid-001/revoke", headers=AUTH_HEADER)
    assert resp.status_code == 200


# -- Kafka audit event ---------------------------------------------------------

@pytest.mark.asyncio
async def test_force_revoke_publishes_audit_event_to_kafka(client, mock_db, mock_kafka):
    """Force-revoke must publish SESSION_FORCE_REVOKED to prana.audit.events."""
    _set_auth(client, role="ciso", user_id="ciso-uuid-001")
    mock_db.fetchrow.return_value = _make_session_row()
    mock_db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    mock_db.execute = AsyncMock(return_value=None)
    jwt = client.app.state.jwt_service
    jwt.revoke = AsyncMock()

    resp = await client.post("/auth/sessions/sess-uuid-001/revoke", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_kafka.auth_event.assert_called_once()
    payload = mock_kafka.auth_event.call_args[0][0]
    assert payload["event_type"] == "SESSION_FORCE_REVOKED"
    assert payload["revoked_session"] == "sess-uuid-001"
    assert payload["tenant_id"] == "tenant-001"


# -- Tenant isolation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_session_revoke_scoped_to_caller_tenant(client, mock_db, mock_kafka):
    """Session from another tenant returns 404 — sessions are tenant-scoped."""
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    # DB returns no row — session exists but belongs to a different tenant
    mock_db.fetchrow.return_value = None

    resp = await client.post("/auth/sessions/sess-from-other-tenant/revoke", headers=AUTH_HEADER)

    assert resp.status_code == 404
    assert "SESSION_NOT_FOUND" in resp.json().get("detail", "")


# -- Already revoked -----------------------------------------------------------

@pytest.mark.asyncio
async def test_force_revoke_already_revoked_session_returns_409(client, mock_db, mock_kafka):
    """Revoking an already-revoked session must return 409 ALREADY_REVOKED."""
    _set_auth(client, role="ciso")
    mock_db.fetchrow.return_value = _make_session_row(revoked=True)

    resp = await client.post("/auth/sessions/sess-uuid-001/revoke", headers=AUTH_HEADER)

    assert resp.status_code == 409
    assert "ALREADY_REVOKED" in resp.json().get("detail", "")
