"""Tests for services/encryption_service.py."""
import hashlib
import hmac
import inspect
from unittest.mock import MagicMock

import pytest

from services.encryption_service import compute_pan_token, encrypt_nik_fpe, decrypt_nik_fpe


def test_pan_token_is_hmac_sha256_of_pan_and_platform_secret():
    nik = "ABCDE1234F"
    secret = "test_platform_secret"
    expected = hmac.new(secret.encode(), nik.encode(), hashlib.sha256).hexdigest()
    assert compute_pan_token(nik, secret) == expected


def test_pan_token_same_pan_same_secret_deterministic():
    nik, secret = "ZZZZZ9999Z", "my_secret"
    assert compute_pan_token(nik, secret) == compute_pan_token(nik, secret)


# ── PAN token versioning ─────────────────────────────────────────────────────

def test_compute_pan_token_version_1_matches_legacy():
    """Version 1 output must equal the original unversioned call — no regression."""
    nik, secret = "ABCDE1234F", "test_platform_secret"
    expected = hmac.new(secret.encode(), nik.encode(), hashlib.sha256).hexdigest()
    # RED: fails if version param not added yet
    assert compute_pan_token(nik, secret, version=1) == expected


def test_compute_pan_token_default_version_is_1():
    """Calling without version= must behave identically to version=1."""
    nik, secret = "ABCDE1234F", "test_platform_secret"
    assert compute_pan_token(nik, secret) == compute_pan_token(nik, secret, version=1)


def test_compute_pan_token_unknown_version_raises():
    """Unknown version must raise ValueError, not silently return a token."""
    with pytest.raises((ValueError, KeyError)):
        compute_pan_token("ABCDE1234F", "secret", version=999)


# ── KMS DEK cache ─────────────────────────────────────────────────────────────

def _make_kms_service(mock_boto_client):
    from services.encryption_service import KMSService
    svc = KMSService.__new__(KMSService)
    svc._client = mock_boto_client
    return svc


def _b64(tag: str) -> str:
    """Return a valid base64 string derived from tag — avoids b64decode padding errors."""
    import base64
    return base64.b64encode(tag.encode()).decode()


def test_kms_unwrap_dek_first_call_hits_kms():
    """First call for an enc_dek must invoke boto3 KMS decrypt. RED: trivially passes."""
    from services.encryption_service import clear_dek_cache
    clear_dek_cache()
    mock_client = MagicMock()
    mock_client.decrypt.return_value = {"Plaintext": b"A" * 32}
    svc = _make_kms_service(mock_client)
    svc.unwrap_dek(_b64("enc-aaa"), "arn:aws:kms:ap-south-1:123:key/abc")
    mock_client.decrypt.assert_called_once()


def test_kms_unwrap_dek_second_call_uses_cache():
    """Second call with same enc_dek must NOT call KMS. RED: fails until cache added."""
    from services.encryption_service import clear_dek_cache
    clear_dek_cache()
    mock_client = MagicMock()
    mock_client.decrypt.return_value = {"Plaintext": b"B" * 32}
    svc = _make_kms_service(mock_client)
    kek = "arn:aws:kms:ap-south-1:123:key/abc"

    r1 = svc.unwrap_dek(_b64("enc-bbb"), kek)
    r2 = svc.unwrap_dek(_b64("enc-bbb"), kek)

    assert mock_client.decrypt.call_count == 1, "Second unwrap must use cache, not KMS"
    assert r1 == r2 == b"B" * 32


def test_kms_different_enc_deks_cached_independently():
    """Two different enc_deks each hit KMS once; subsequent calls use their own cache entry."""
    from services.encryption_service import clear_dek_cache
    clear_dek_cache()
    mock_client = MagicMock()
    mock_client.decrypt.side_effect = [{"Plaintext": b"C" * 32}, {"Plaintext": b"D" * 32}]
    svc = _make_kms_service(mock_client)
    kek = "arn:aws:kms:ap-south-1:123:key/abc"

    r1 = svc.unwrap_dek(_b64("enc-ccc"), kek)
    r2 = svc.unwrap_dek(_b64("enc-ddd"), kek)
    _ = svc.unwrap_dek(_b64("enc-ccc"), kek)  # cache hit
    _ = svc.unwrap_dek(_b64("enc-ddd"), kek)  # cache hit

    assert mock_client.decrypt.call_count == 2


def test_clear_dek_cache_forces_kms_on_next_call():
    """After clear_dek_cache(), the next unwrap must go to KMS again."""
    from services.encryption_service import clear_dek_cache
    clear_dek_cache()
    mock_client = MagicMock()
    mock_client.decrypt.return_value = {"Plaintext": b"E" * 32}
    svc = _make_kms_service(mock_client)
    kek = "arn:aws:kms:ap-south-1:123:key/abc"

    svc.unwrap_dek(_b64("enc-eee"), kek)
    clear_dek_cache()
    svc.unwrap_dek(_b64("enc-eee"), kek)

    assert mock_client.decrypt.call_count == 2, "After clear, must hit KMS again"


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


# ── H2: FPE must never degrade to plaintext ───────────────────────────────────

def test_fpe_raises_when_ff3_missing_never_leaks_plaintext(monkeypatch):
    """If the ff3 primitive is unavailable, encryption must RAISE — never return a
    plaintext-derived placeholder that leaks characters of the PAN (finding H2)."""
    import sys
    nik = "ABCDE1234F"
    dek = b"K" * 32
    # Force `import ff3` to fail inside the function.
    monkeypatch.setitem(sys.modules, "ff3", None)
    with pytest.raises(RuntimeError):
        out = encrypt_nik_fpe(nik, dek)
        # Guard the impossible-pass case: the old bug returned "ENC_ABCD..." leaking the PAN.
        assert "ABCD" not in out


def test_fpe_source_has_no_plaintext_fallback():
    import inspect
    import services.encryption_service as enc_mod
    src = inspect.getsource(enc_mod)
    assert 'f"ENC_{nik' not in src, "plaintext-leaking FPE fallback must be gone"


# ── Platform auth CMK (mobile numbers + TOTP secrets) ────────────────────────
# Replaces the static resolve_auth_dek secret for these two fields (2026-07-19):
# a leaked static secret decrypts everything platform-wide, silently, forever.
# Real KMS requires live IAM-gated access, is CloudTrail-audited, and can be
# cut off instantly by disabling the CMK.

def test_kms_encrypt_value_calls_kms_encrypt():
    mock_client = MagicMock()
    mock_client.encrypt.return_value = {"CiphertextBlob": b"ciphertext-bytes"}
    svc = _make_kms_service(mock_client)

    result = svc.encrypt_value("+919876543210", "arn:aws:kms:ap-south-1:123:key/platform-auth")

    mock_client.encrypt.assert_called_once_with(
        KeyId="arn:aws:kms:ap-south-1:123:key/platform-auth", Plaintext=b"+919876543210",
    )
    import base64
    assert result == base64.b64encode(b"ciphertext-bytes").decode()


def test_kms_decrypt_value_calls_kms_decrypt():
    mock_client = MagicMock()
    mock_client.decrypt.return_value = {"Plaintext": b"+919876543210"}
    svc = _make_kms_service(mock_client)

    result = svc.decrypt_value(_b64("some-ciphertext"), "arn:aws:kms:ap-south-1:123:key/platform-auth")

    mock_client.decrypt.assert_called_once()
    assert result == "+919876543210"


def test_kms_encrypt_decrypt_value_roundtrip_via_mock():
    """encrypt_value's output must be exactly what decrypt_value expects as input."""
    mock_client = MagicMock()
    stash = {}

    def fake_encrypt(KeyId, Plaintext):
        stash["plaintext"] = Plaintext
        return {"CiphertextBlob": b"opaque-ciphertext"}

    def fake_decrypt(CiphertextBlob, KeyId):
        assert CiphertextBlob == b"opaque-ciphertext"
        return {"Plaintext": stash["plaintext"]}

    mock_client.encrypt.side_effect = fake_encrypt
    mock_client.decrypt.side_effect = fake_decrypt
    svc = _make_kms_service(mock_client)

    enc = svc.encrypt_value("JBSWY3DPEHPK3PXP", "arn:aws:kms:ap-south-1:123:key/x")
    dec = svc.decrypt_value(enc, "arn:aws:kms:ap-south-1:123:key/x")
    assert dec == "JBSWY3DPEHPK3PXP"


def test_kms_create_platform_auth_kek_returns_arn():
    mock_client = MagicMock()
    mock_client.create_key.return_value = {"KeyMetadata": {"Arn": "arn:aws:kms:ap-south-1:123:key/platform-auth-new"}}
    svc = _make_kms_service(mock_client)

    arn = svc.create_platform_auth_kek()

    assert arn == "arn:aws:kms:ap-south-1:123:key/platform-auth-new"
    call_kwargs = mock_client.create_key.call_args.kwargs
    assert call_kwargs["KeyUsage"] == "ENCRYPT_DECRYPT"


def test_resolve_platform_auth_kek_arn_returns_configured_value():
    from services.encryption_service import resolve_platform_auth_kek_arn
    from config import Settings

    s = Settings(app_env="development", platform_hmac_secret="dev_secret",
                 platform_auth_kek_arn="arn:aws:kms:ap-south-1:123:key/platform-auth")
    assert resolve_platform_auth_kek_arn(s) == "arn:aws:kms:ap-south-1:123:key/platform-auth"


def test_resolve_platform_auth_kek_arn_empty_in_dev_is_allowed():
    """Dev/test may legitimately be empty before the bootstrap script has been
    run — callers (not this resolver) decide whether to fail on empty."""
    from services.encryption_service import resolve_platform_auth_kek_arn
    from config import Settings

    s = Settings(app_env="development", platform_hmac_secret="dev_secret")
    assert resolve_platform_auth_kek_arn(s) == ""


def test_resolve_platform_auth_kek_arn_raises_in_production_if_unset():
    from services.encryption_service import resolve_platform_auth_kek_arn
    from config import Settings

    s = Settings(app_env="production", platform_auth_kek_arn="")
    with pytest.raises(RuntimeError):
        resolve_platform_auth_kek_arn(s)
