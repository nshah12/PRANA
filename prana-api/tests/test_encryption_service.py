"""Tests for services/encryption_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pan_token_is_hmac_sha256_of_pan_and_platform_secret():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pan_token_same_pan_same_secret_deterministic():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_enc_pan_is_reversible_with_correct_dek():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_raw_pan_never_stored_only_enc_pan_and_token():
    raise NotImplementedError
