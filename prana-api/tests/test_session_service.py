"""Tests for services/session_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_create_session_returns_jti_stored_in_user_session():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_revoke_session_sets_revoked_true():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_revoked_jti_cached_in_redis_with_ttl():
    raise NotImplementedError
