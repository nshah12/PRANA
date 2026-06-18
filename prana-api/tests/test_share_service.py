"""Tests for services/share_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_create_share_token_stored_in_redis_with_config_ttl():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_share_otp_sent_to_recipient_not_owner():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_max_active_shares_per_doc_enforced_from_config():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_revoke_share_deletes_redis_key():
    raise NotImplementedError
