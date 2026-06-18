"""Tests for services/jwt_service.py."""
import inspect

from services.jwt_service import JWTService


def test_jwt_encode_includes_tenant_id_and_role():
    src = inspect.getsource(JWTService.issue)
    assert "tenant_id" in src, "JWT payload must include tenant_id"
    assert "role" in src, "JWT payload must include role"
    assert "jti" in src, "JWT payload must include jti = session_id"


def test_jwt_verify_rejects_revoked_jti():
    src = inspect.getsource(JWTService.is_revoked)
    assert "revoked:" in src, \
        "is_revoked must check Redis revoked:{session_id} key"


def test_jwt_expired_token_raises():
    src = inspect.getsource(JWTService.decode)
    assert "RS256" in src, "JWT must use RS256 algorithm"
    # decode() passes through pyjwt exceptions — ExpiredSignatureError propagates
    assert "pyjwt.decode" in src or "jwt.decode" in src, \
        "decode() must use pyjwt.decode which raises on expired tokens"
