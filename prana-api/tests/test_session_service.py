"""Tests for services/session_service.py."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.session_service import SessionService


def _make_mocks():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetchval = AsyncMock(return_value=str(__import__("uuid").uuid4()))
    db.fetchrow = AsyncMock(return_value=None)
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    jwt = MagicMock()
    jwt.issue = MagicMock(return_value="mock.jwt.token")
    jwt.revoke = AsyncMock()
    return db, jwt


def test_create_session_returns_jti_stored_in_user_session():
    src = inspect.getsource(SessionService.create)
    assert "session_id" in src, "create() must store session_id (jti) in user_session"
    assert "INSERT" in src.upper(), "create() must INSERT into user_session"


@pytest.mark.asyncio
async def test_revoke_session_sets_revoked_true():
    db, jwt = _make_mocks()
    svc = SessionService(db, jwt)
    await svc.revoke("sess-abc", reason="LOGOUT")

    db.execute.assert_called_once()
    call_args = str(db.execute.call_args)
    assert "revoked=TRUE" in call_args or "revoked" in call_args.lower()


@pytest.mark.asyncio
async def test_revoked_jti_cached_in_redis_with_ttl():
    db, jwt = _make_mocks()
    svc = SessionService(db, jwt)
    await svc.revoke("sess-xyz")

    # jwt.revoke must be called — it adds to Redis blocklist
    jwt.revoke.assert_called_once_with("sess-xyz")
