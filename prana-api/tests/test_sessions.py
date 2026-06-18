"""Tests for routers/sessions.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_force_revoke_session_requires_ciso_or_oa_admin():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_force_revoke_publishes_audit_event_to_kafka():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_session_revoke_scoped_to_caller_tenant():
    raise NotImplementedError
