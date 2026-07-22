"""Tests for pipeline/stage02_encrypt.py — encryption contract and NIK handling."""
import hashlib
import hmac
import inspect

import pytest

from pipeline.stage02_encrypt import Stage02Encrypt, _ff3_encrypt_pan
from pipeline.errors import PipelineException, PipelineError


def test_stage02_zeroes_nik_from_memory_after_tokenisation():
    src = inspect.getsource(Stage02Encrypt.run)
    # After HMAC + FF3 computation the code must overwrite and delete the NIK variable
    assert 'nik = "0"' in src or "nik = b'0'" in src or 'nik = None' in src, \
        "Stage02 must zero NIK from memory immediately after pan_token and enc_pan are computed"
    assert "del nik" in src, \
        "Stage02 must explicitly del nik after use to reduce time raw PAN is in memory"


def test_stage02_pan_token_is_hmac_sha256():
    src = inspect.getsource(Stage02Encrypt.run)
    assert "hmac.new" in src or "hmac.new" in src, \
        "pan_token computation must use hmac.new() (HMAC-SHA256)"
    assert "hashlib.sha256" in src, \
        "pan_token HMAC must use SHA-256"


def test_stage02_enc_pan_uses_ff3_fpe():
    src = inspect.getsource(Stage02Encrypt.run)
    # FF3-1 Format-Preserving Encryption is used for enc_pan
    assert "_ff3_encrypt_pan" in src, \
        "enc_pan must be computed via _ff3_encrypt_pan (FF3-1 FPE), not plain AES-GCM"


def test_stage02_raw_pan_never_written_to_db():
    # Stage02 has no DB connection — it only writes to S3 and returns a dict.
    # The raw PAN is never stored anywhere; only pan_token and enc_pan leave this stage.
    src = inspect.getsource(Stage02Encrypt.run)
    assert "db." not in src and "asyncpg" not in src, \
        "Stage02 must not touch the database — only S3 writes and returned dict"
    # Verify the return dict contains pan_token and enc_pan but NOT raw nik
    assert '"pan_token"' in src or "'pan_token'" in src, \
        "run() must include pan_token in its return dict"
    assert '"nik"' not in src and "'nik'" not in src, \
        "run() must NOT include raw nik in its return dict"


def test_ff3_encrypt_pan_never_falls_back_to_reversible_placeholder(monkeypatch):
    """
    Regression test: _ff3_encrypt_pan used to catch any exception (missing `ff3`
    package, unexpected PAN format) and silently return
    "ENC" + base64.urlsafe_b64encode(pan.encode())[:7] — trivially reversible with
    no key at all. That is the exact "finding H2" anti-pattern
    prana-api/services/encryption_service.py documents as a fixed, banned bug class
    ("NEVER degrade to a plaintext-derived placeholder ... that would leak the
    PAN. A missing crypto primitive is a hard failure."). A missing/failing FF3
    primitive here must raise, never emit reversible pseudo-ciphertext.
    """
    import builtins
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "ff3":
            raise ImportError("simulated: ff3 package not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    with pytest.raises(PipelineException) as exc_info:
        _ff3_encrypt_pan("ABCDE1234F", b"0" * 16)

    assert exc_info.value.code == PipelineError.S02_ENCRYPT_FF3_PAN_FAILED
    # The raw PAN must never appear, reversibly encoded or otherwise, in the exception
    assert "ABCDE1234F" not in str(exc_info.value)
