"""Tests for workflows/vault_shares.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_share_expiry_workflow_uses_durable_timer():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_share_revocation_signal_cancels_expiry_timer():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_share_ttl_from_platform_config_not_hardcoded():
    raise NotImplementedError
