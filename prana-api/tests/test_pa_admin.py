"""Tests for routers/pa_admin.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_activate_tenant_requires_portal_admin_role():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_tenant_activation_publishes_audit_event_to_kafka():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_emergency_override_publishes_audit_event_to_kafka():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_pa_admin_can_target_any_tenant_cross_tenant_ok():
    raise NotImplementedError
