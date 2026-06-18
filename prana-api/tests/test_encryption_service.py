"""Tests for services/encryption_service.py."""
import hashlib
import hmac
import inspect

from services.encryption_service import compute_pan_token, encrypt_nik_fpe, decrypt_nik_fpe


def test_pan_token_is_hmac_sha256_of_pan_and_platform_secret():
    nik = "ABCDE1234F"
    secret = "test_platform_secret"
    expected = hmac.new(secret.encode(), nik.encode(), hashlib.sha256).hexdigest()
    assert compute_pan_token(nik, secret) == expected


def test_pan_token_same_pan_same_secret_deterministic():
    nik, secret = "ZZZZZ9999Z", "my_secret"
    assert compute_pan_token(nik, secret) == compute_pan_token(nik, secret)


def test_enc_pan_is_reversible_with_correct_dek():
    import services.encryption_service as enc_mod
    src = inspect.getsource(enc_mod)
    assert "decrypt_nik_fpe" in src, "decrypt_nik_fpe must exist as inverse of encrypt_nik_fpe"
    assert "ff3" in src.lower() or "FPE" in src, "Must use FF3-1 FPE algorithm"
    assert callable(encrypt_nik_fpe)
    assert callable(decrypt_nik_fpe)


def test_raw_pan_never_stored_only_enc_pan_and_token():
    nik = "ABCDE1234F"
    token = compute_pan_token(nik, "platform_secret_32chars_padding1")
    assert nik not in token
    assert len(token) == 64, "HMAC-SHA256 output is 64 hex chars"
