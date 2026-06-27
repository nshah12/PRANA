"""Tests for SecurityConsumer — prana.security.events"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def redis():
    r = AsyncMock()
    r.publish = AsyncMock()
    return r


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool, redis):
    from kafka.consumers.security_consumer import SecurityConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return SecurityConsumer(settings, db_pool=pool, temporal_client=temporal, redis=redis)


@pytest.mark.asyncio
async def test_anomaly_detected_publishes_sse_alert(consumer, db_pool, redis):
    _, conn = db_pool
    conn.execute = AsyncMock()
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1",
             "user_id": "u-1", "anomaly_type": "UNUSUAL_ACCESS"}
    await consumer._dispatch("ANOMALY_DETECTED", event)
    redis.publish.assert_awaited_once()
    channel = redis.publish.call_args[0][0]
    assert "sse:tenant:t-1:alerts" == channel


@pytest.mark.asyncio
async def test_csam_detected_starts_reporting_workflow(consumer):
    event = {"event_type": "CSAM_DETECTED", "tenant_id": "t-1", "document_id": "d-1"}
    await consumer._dispatch("CSAM_DETECTED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_locked_publishes_sse_alert(consumer, db_pool, redis):
    _, conn = db_pool
    conn.execute = AsyncMock()
    event = {"event_type": "ACCOUNT_LOCKED", "tenant_id": "t-1", "user_id": "u-2"}
    await consumer._dispatch("ACCOUNT_LOCKED", event)
    redis.publish.assert_awaited()
