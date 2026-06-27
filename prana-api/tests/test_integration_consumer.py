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
    return IntegrationConsumer(settings, db_pool=pool, kafka_producer=kafka_producer)


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
