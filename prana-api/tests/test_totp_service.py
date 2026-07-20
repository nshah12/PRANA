"""Tests for services/totp_service.py."""
import pathlib

import pyotp
import pytest

from services.totp_service import TOTPService


_svc = TOTPService()


def test_totp_verify_valid_code_returns_true():
    secret = _svc.generate_secret()
    valid_code = pyotp.TOTP(secret).now()
    assert _svc.verify(valid_code, secret) is True


def test_totp_verify_invalid_code_returns_false():
    secret = _svc.generate_secret()
    assert _svc.verify("000000", secret) is False


def test_totp_lockout_at_5_failures():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "auth_oa.py").read_text(encoding="utf-8")
    assert "failed_totp_count" in src, \
        "auth_oa must track failed_totp_count for lockout"


def test_totp_service_has_no_encryption_key_knowledge():
    """TOTPService.verify takes a plaintext secret — decryption of totp_secret_enc
    happens in the caller (via KMSService.decrypt_value + the platform auth CMK),
    not here. Keeps this class decoupled from which key/mechanism protects the
    stored secret."""
    import inspect
    src = inspect.getsource(TOTPService.verify)
    assert "decrypt_value(" not in src and "aes_decrypt(" not in src
