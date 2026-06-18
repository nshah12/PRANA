"""Tests for routers/totp_setup.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_provision_returns_qr_code_not_raw_secret():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_verify_confirms_setup():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_totp_secret_never_returned_in_api_response():
    raise NotImplementedError
