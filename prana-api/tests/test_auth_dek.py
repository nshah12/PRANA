"""Tests for resolve_auth_dek — the AES key used to encrypt TOTP & HRMS signing secrets.

Finding C1: previously every auth flow used b"\\x00" * 32 (a publicly-known all-zero key),
making 2FA seeds and signing secrets effectively plaintext. resolve_auth_dek must:
  - NEVER return an all-zero key
  - derive a stable non-zero key in dev/test (works without AWS)
  - require a real injected key in production, and reject a zero/short one
"""
import hashlib

import pytest

from config import Settings
from services.encryption_service import resolve_auth_dek, aes_encrypt, aes_decrypt


def test_dev_dek_is_never_all_zero():
    s = Settings(app_env="development", platform_hmac_secret="dev_secret")
    dek = resolve_auth_dek(s)
    assert dek != b"\x00" * 32
    assert len(dek) == 32


def test_dev_dek_is_deterministic():
    s1 = Settings(app_env="development", platform_hmac_secret="same_secret")
    s2 = Settings(app_env="development", platform_hmac_secret="same_secret")
    assert resolve_auth_dek(s1) == resolve_auth_dek(s2)


def test_dev_dek_changes_with_platform_secret():
    a = resolve_auth_dek(Settings(app_env="development", platform_hmac_secret="secret_a"))
    b = resolve_auth_dek(Settings(app_env="development", platform_hmac_secret="secret_b"))
    assert a != b


def test_explicit_hex_key_is_used_verbatim():
    key_hex = "ab" * 32
    s = Settings(app_env="production", auth_encryption_key=key_hex,
                 platform_hmac_secret="real", db_password="real",
                 ai_service_secret="real", ask_service_secret="real",
                 jwt_kms_key_id="arn:x")
    assert resolve_auth_dek(s) == bytes.fromhex(key_hex)


def test_production_without_key_raises():
    s = Settings(app_env="production", auth_encryption_key="")
    with pytest.raises(RuntimeError):
        resolve_auth_dek(s)


def test_explicit_all_zero_key_rejected():
    s = Settings(app_env="production", auth_encryption_key="00" * 32)
    with pytest.raises(ValueError):
        resolve_auth_dek(s)


def test_explicit_wrong_length_key_rejected():
    s = Settings(app_env="production", auth_encryption_key="abcd")  # 2 bytes
    with pytest.raises(ValueError):
        resolve_auth_dek(s)


def test_dek_actually_encrypts_and_decrypts_roundtrip():
    """The resolved key must be a usable AES-256-GCM key end to end."""
    dek = resolve_auth_dek(Settings(app_env="development", platform_hmac_secret="dev_secret"))
    token = aes_encrypt("JBSWY3DPEHPK3PXP", dek)
    assert aes_decrypt(token, dek) == "JBSWY3DPEHPK3PXP"


def test_no_router_reintroduces_all_zero_key():
    """Regression guard for C1: no auth/crypto handler may hardcode the all-zero DEK again."""
    import pathlib
    import re
    routers = pathlib.Path(__file__).resolve().parent.parent / "routers"
    offenders = [
        p.name for p in routers.glob("*.py")
        if re.search(r'b"\\x00"\s*\*\s*32', p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"all-zero DEK reintroduced in: {offenders}"
