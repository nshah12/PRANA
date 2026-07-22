"""Tests for IntegrationConsumer — prana.integrations.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.integration_consumer import IntegrationConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    kafka_producer = AsyncMock()
    temporal_client = AsyncMock()
    return IntegrationConsumer(settings, db_pool=pool, kafka_producer=kafka_producer,
                                temporal_client=temporal_client)


@pytest.mark.asyncio
async def test_hrms_webhook_failed_increments_retry(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"retry_count": 1}
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "tenant_id": "t-1",
             "filename": "salaryslip.pdf", "reason": "INVALID_FORMAT"}
    await consumer._handle(event)
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_hrms_webhook_failed_max_retries_no_more_increment(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"retry_count": 3}  # at max
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "tenant_id": "t-1", "filename": "doc.pdf"}
    await consumer._handle(event)
    # Should not try to update past max retries


@pytest.mark.asyncio
async def test_epfo_verification_failed_sets_exception_status(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "EPFO_VERIFICATION_FAILED", "document_id": "d-1", "tenant_id": "t-1"}
    await consumer._handle(event)
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_kms_health_failed_escalates(consumer):
    event = {"event_type": "KMS_HEALTH_FAILED", "tenant_id": "t-1", "region": "ap-south-1"}
    await consumer._handle(event)
    consumer._kafka.platform_event.assert_awaited_once()


# ── HRMS_CONNECTOR_STATUS_CHANGED ────────────────────────────────────────────
# Regression: create_config/pause_connector/resume_connector in hrms_config.py
# published no event at all, so nothing ever ensured a Temporal Schedule
# existed for a tenant's connectors despite HRMSSyncScheduleWorkflow's own
# docstring claiming it's "safe to run on every tenant provisioning or
# connector status change" — this is that "or connector status change" path.

@pytest.mark.asyncio
async def test_connector_status_changed_starts_hrms_sync_schedule_workflow(consumer):
    from workflows.hrms_sync_schedule import HRMSSyncScheduleWorkflow

    event = {"event_type": "HRMS_CONNECTOR_STATUS_CHANGED", "tenant_id": "t-1",
             "connector_id": "c-1", "status": "ACTIVE"}
    await consumer._handle(event)

    consumer._temporal.start_workflow.assert_awaited_once()
    args, kwargs = consumer._temporal.start_workflow.call_args
    assert args[0] is HRMSSyncScheduleWorkflow.run
    assert args[1].tenant_id == "t-1"
    assert kwargs["task_queue"] == "hrms-queue"
    assert kwargs["id"] == "hrms-sync-schedule-t-1"


@pytest.mark.asyncio
async def test_connector_status_changed_missing_temporal_client_is_noop(db_pool):
    """No temporal_client wired (e.g. dev/test) — must not crash the consumer."""
    from kafka.consumers.integration_consumer import IntegrationConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    c = IntegrationConsumer(settings, db_pool=pool, kafka_producer=AsyncMock(), temporal_client=None)

    event = {"event_type": "HRMS_CONNECTOR_STATUS_CHANGED", "tenant_id": "t-1"}
    await c._handle(event)  # must not raise
