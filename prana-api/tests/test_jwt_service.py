"""Tests for services/jwt_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_jwt_encode_includes_tenant_id_and_role():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_jwt_verify_rejects_revoked_jti():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_jwt_expired_token_raises():
    raise NotImplementedError
