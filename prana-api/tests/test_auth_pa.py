"""Tests for routers/auth_pa.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pa_login_valid_credentials_returns_jwt():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pa_login_wrong_password_returns_401():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pa_totp_invalid_lockout():
    raise NotImplementedError
