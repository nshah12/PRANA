"""Tests for services/totp_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_verify_valid_code_returns_true():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_verify_invalid_code_increments_failed_count():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_lockout_at_5_failures():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_secret_stored_encrypted_never_plaintext():
    raise NotImplementedError
