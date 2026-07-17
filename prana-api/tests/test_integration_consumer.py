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
async def test_hrms_webhook_failed_creates_row_on_first_failure(consumer, db_pool):
    """First failure for a request_id: INSERT branch of the upsert fires, retry_count=1."""
    _, conn = db_pool
    conn.fetchrow.return_value = {"retry_count": 1}
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "request_id": "r-1", "tenant_id": "t-1",
             "filename": "salaryslip.pdf", "reason": "INVALID_FORMAT"}
    await consumer._handle(event)
    conn.fetchrow.assert_awaited_once()
    args = conn.fetchrow.await_args.args
    assert "api_ingest_log" in args[0]
    assert args[1:] == ("r-1", "t-1", "salaryslip.pdf", "INVALID_FORMAT", 3)


@pytest.mark.asyncio
async def test_hrms_webhook_failed_increments_retry_on_repeat_failure(consumer, db_pool):
    """Repeat failure for the same request_id: ON CONFLICT DO UPDATE branch fires."""
    _, conn = db_pool
    conn.fetchrow.return_value = {"retry_count": 2}
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "request_id": "r-1", "tenant_id": "t-1",
             "filename": "doc.pdf"}
    await consumer._handle(event)
    conn.fetchrow.assert_awaited_once()


@pytest.mark.asyncio
async def test_hrms_webhook_failed_max_retries_no_more_increment(consumer, db_pool):
    """WHERE retry_count < max_retries fails on the 4th attempt — RETURNING yields nothing."""
    _, conn = db_pool
    conn.fetchrow.return_value = None  # simulates the ON CONFLICT ... WHERE clause not matching
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "request_id": "r-1", "tenant_id": "t-1", "filename": "doc.pdf"}
    await consumer._handle(event)
    # Should not raise — exhausted-retries path just logs and returns


@pytest.mark.asyncio
async def test_hrms_webhook_failed_missing_request_id_skips_db_write(consumer, db_pool):
    """Without a request_id there is nothing to key the upsert on — must not hit the DB."""
    _, conn = db_pool
    event = {"event_type": "HRMS_WEBHOOK_FAILED", "tenant_id": "t-1", "filename": "doc.pdf"}
    await consumer._handle(event)
    conn.fetchrow.assert_not_awaited()


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
