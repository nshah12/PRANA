"""Tests for KMS-backed RS256 JWT signing (finding C4).

Dev/test sign with the local PEM. Production must sign via KMS so the private key
never leaves the HSM. JWTService.issue() must pick the right path and never raise
"KMS signing not implemented".
"""
import base64
import json
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest

from config import Settings
from services.jwt_service import JWTService


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def _dev_service():
    """Real JWTService with local PEM (app_env=test → local key path loaded)."""
    s = Settings(app_env="test")
    return JWTService(s, MagicMock())


def test_dev_issue_uses_local_pem_and_verifies():
    svc = _dev_service()
    token = svc.issue(user_type="oa_user", user_id="u1", tenant_id="t1",
                      role="oa_admin", session_id="sess-1", ttl_minutes=5)
    claims = svc.decode(token)
    assert claims["sub"] == "u1"
    assert claims["jti"] == "sess-1"
    assert claims["tenant_id"] == "t1"


def test_prod_without_local_key_signs_via_kms():
    """In production with a KMS key id, issue() must call KMS sign, not raise."""
    s = Settings(app_env="production", jwt_kms_key_id="arn:aws:kms:ap-south-1:1:key/abc",
                 platform_hmac_secret="real", db_password="real",
                 ai_service_secret="real", ask_service_secret="real",
                 auth_encryption_key="ab" * 32)
    kms = MagicMock()
    kms.sign_jwt.return_value = b"\x01\x02\x03fake-sig"
    svc = JWTService(s, MagicMock(), kms_service=kms)

    token = svc.issue(user_type="oa_user", user_id="u9", tenant_id="t9",
                      role="cfo", session_id="sess-9", ttl_minutes=10)

    # KMS must have been asked to sign with the configured key
    kms.sign_jwt.assert_called_once()
    _, called_key = kms.sign_jwt.call_args[0]
    assert called_key == "arn:aws:kms:ap-south-1:1:key/abc"

    # Token is a well-formed 3-part JWS whose payload carries our claims
    header_seg, payload_seg, sig_seg = token.split(".")
    header = json.loads(_b64url_decode(header_seg))
    payload = json.loads(_b64url_decode(payload_seg))
    assert header["alg"] == "RS256"
    assert payload["sub"] == "u9"
    assert payload["jti"] == "sess-9"
    assert _b64url_decode(sig_seg) == b"\x01\x02\x03fake-sig"


def test_prod_without_key_or_kms_raises_clearly():
    """No local key AND no KMS configured → must raise, never emit an unsigned token."""
    s = Settings(app_env="production", jwt_kms_key_id="",
                 platform_hmac_secret="real", db_password="real",
                 ai_service_secret="real", ask_service_secret="real",
                 auth_encryption_key="ab" * 32)
    svc = JWTService(s, MagicMock(), kms_service=None)
    with pytest.raises(RuntimeError):
        svc.issue(user_type="oa_user", user_id="u", tenant_id="t",
                  role="cfo", session_id="s", ttl_minutes=5)
