"""Tests for routers/compliance.py and workflows/compliance.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_erasure_request_publishes_to_kafka_not_starts_workflow_directly():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_erasure_does_not_delete_audit_event_rows():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_consent_withdrawal_is_immediate():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_grievance_publishes_to_kafka():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_export_request_publishes_to_kafka():
    raise NotImplementedError
