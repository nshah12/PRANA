"""Tests for TenantConsumer — prana.tenant.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def consumer():
    from kafka.consumers.tenant_consumer import TenantConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    temporal = AsyncMock()
    return TenantConsumer(settings, temporal_client=temporal, db_pool=MagicMock())


@pytest.mark.asyncio
async def test_tenant_created_starts_provisioning_workflow(consumer):
    event = {"event_type": "TENANT_CREATED", "tenant_id": "t-1", "domain": "co.com"}
    await consumer._dispatch("TENANT_CREATED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    assert "t-1" in consumer._temporal.start_workflow.call_args[1]["id"]


@pytest.mark.asyncio
async def test_tenant_suspended_starts_suspension_workflow(consumer):
    event = {"event_type": "TENANT_SUSPENDED", "tenant_id": "t-2", "reason": "nonpayment"}
    await consumer._dispatch("TENANT_SUSPENDED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_kek_rotated_starts_rotation_workflow(consumer):
    event = {"event_type": "KEK_ROTATED", "tenant_id": "t-3"}
    await consumer._dispatch("KEK_ROTATED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_already_running_is_idempotent(consumer):
    consumer._temporal.start_workflow.side_effect = Exception("already exists")
    event = {"event_type": "TENANT_CREATED", "tenant_id": "t-4", "domain": "co.com"}
    await consumer._dispatch("TENANT_CREATED", event)  # must not raise
