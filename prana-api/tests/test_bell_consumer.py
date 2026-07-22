"""Tests for BellConsumer — prana.notifications.portal_bell"""
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
    from kafka.consumers.bell_consumer import BellConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    return BellConsumer(settings, db_pool=pool, redis=redis)


@pytest.mark.asyncio
async def test_bell_published_to_correct_redis_channel(consumer, db_pool, redis):
    _, conn = db_pool
    event = {"event_type": "OBLIGATION_DUE", "recipient_id": "u-chro",
             "template_id": "OBLIGATION_DUE", "tenant_id": "t-1",
             "payload": {"act": "EPF_ACT"}}
    await consumer._handle(event)
    redis.publish.assert_awaited_once()
    channel = redis.publish.call_args[0][0]
    assert channel == "sse:user:u-chro:bells"


@pytest.mark.asyncio
async def test_bell_payload_contains_event_type(consumer, db_pool, redis):
    _, conn = db_pool
    event = {"event_type": "ELEVATION_EXPIRED", "recipient_id": "u-op",
             "template_id": "ELEVATION_EXPIRED", "tenant_id": "t-1", "payload": {}}
    await consumer._handle(event)
    published_data = json.loads(redis.publish.call_args[0][1])
    assert published_data["event_type"] == "ELEVATION_EXPIRED"


@pytest.mark.asyncio
async def test_bell_inserts_to_notification_log(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "OBLIGATION_DUE", "recipient_id": "u-cfo",
             "template_id": "OBLIGATION_DUE", "tenant_id": "t-1", "payload": {}}
    await consumer._handle(event)
    conn.execute.assert_awaited()
