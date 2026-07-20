"""
Tests for kafka/consumers/workflow_consumer.py — DOMAIN_VERIFICATION_REQUESTED handling.

Covers: WorkflowConsumer must start DomainVerificationWorkflow when it sees a
DOMAIN_VERIFICATION_REQUESTED event — tenants.py's create_tenant already
publishes this event, but nothing consumed it, so domain verification never
actually started for a newly-created tenant.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from kafka.consumers.workflow_consumer import WorkflowConsumer


def _make_consumer():
    settings = MagicMock()
    temporal = AsyncMock()
    consumer = WorkflowConsumer(settings, temporal)
    return consumer, temporal


@pytest.mark.asyncio
async def test_domain_verification_requested_starts_workflow():
    consumer, temporal = _make_consumer()
    event = {
        "event_type": "DOMAIN_VERIFICATION_REQUESTED",
        "tenant_id": "tenant-xyz",
        "domain": "acme.com",
        "workflow_id": "domain-verify-tenant-xyz",
    }

    await consumer._handle_domain_verification_requested(event)

    temporal.start_workflow.assert_called_once()
    call = temporal.start_workflow.call_args
    assert call.kwargs["id"] == "domain-verify-tenant-xyz"
    args_payload = call.args[1]
    assert args_payload["tenant_id"] == "tenant-xyz"
    assert args_payload["domain"] == "acme.com"


@pytest.mark.asyncio
async def test_domain_verification_requested_is_idempotent_on_already_started():
    consumer, temporal = _make_consumer()
    temporal.start_workflow = AsyncMock(side_effect=Exception("Workflow already started"))
    event = {
        "tenant_id": "tenant-xyz", "domain": "acme.com",
        "workflow_id": "domain-verify-tenant-xyz",
    }

    await consumer._handle_domain_verification_requested(event)  # must not raise
