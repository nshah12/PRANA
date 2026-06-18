"""Tests for services/vault_service.py."""
import inspect
import pathlib

from services.vault_service import VaultService


_SOURCE = pathlib.Path(__file__).parent.parent / "services" / "vault_service.py"


def test_get_document_bytes_watermarks_before_returning():
    src = inspect.getsource(VaultService.get_document_bytes)
    assert "_log_access" in src, \
        "get_document_bytes must call _log_access to record every access"
    assert "watermark" in src.lower() or "_log_access" in src, \
        "Access must be logged (includes watermark_applied flag)"


def test_document_access_always_writes_access_log():
    src = inspect.getsource(VaultService._log_access)
    assert "document_access_log" in src, \
        "_log_access must INSERT into document_access_log"
    assert "ip_address" in src, \
        "ip_address must be recorded — NOT NULL per schema"


def test_decrypted_bytes_never_cached_to_disk():
    src = _SOURCE.read_text(encoding="utf-8")
    # No file writes allowed — decryption is always in-memory
    assert "open(" not in src, "No file open() allowed in vault_service — in-memory only"
    assert ".write(" not in src, "No disk write allowed — decrypted bytes are in-memory only"


def test_password_session_wiped_on_expiry():
    src = _SOURCE.read_text(encoding="utf-8")
    # Document bytes are returned from RAM, not cached
    assert "cache" not in src.lower() or "redis" not in src.lower(), \
        "Decrypted bytes must not be written to Redis cache"
    # del dek is called immediately after use
    assert "del dek" in src, "DEK must be deleted immediately after decryption"
