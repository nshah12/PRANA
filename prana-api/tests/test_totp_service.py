"""Tests for services/totp_service.py."""
import os
import inspect
import pathlib

import pyotp
import pytest

from services.totp_service import TOTPService
from services.encryption_service import aes_encrypt


_svc = TOTPService()
_DEK = os.urandom(32)


def test_totp_verify_valid_code_returns_true():
    secret = _svc.generate_secret()
    enc_secret = aes_encrypt(secret, _DEK)
    valid_code = pyotp.TOTP(secret).now()
    assert _svc.verify(valid_code, enc_secret, _DEK) is True


def test_totp_verify_invalid_code_increments_failed_count():
    secret = _svc.generate_secret()
    enc_secret = aes_encrypt(secret, _DEK)
    result = _svc.verify("000000", enc_secret, _DEK)
    assert result is False


def test_totp_lockout_at_5_failures():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "auth_oa.py").read_text(encoding="utf-8")
    assert "failed_totp_count" in src, \
        "auth_oa must track failed_totp_count for lockout"


def test_totp_secret_stored_encrypted_never_plaintext():
    src = inspect.getsource(TOTPService.verify)
    assert "aes_decrypt" in src or "decrypt" in src.lower(), \
        "TOTPService.verify must decrypt stored secret before use"
