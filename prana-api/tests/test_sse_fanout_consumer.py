"""
SSEFanoutConsumer unit tests — TDD RED → GREEN → REFACTOR

Tests the Kafka → Redis Pub/Sub fanout layer.

Flow under test:
  prana.pipeline.events (Kafka) → SSEFanoutConsumer → redis.publish("sse:doc:{id}", payload)

Contracts verified:
  1. Publishes to channel sse:doc:{document_id}
  2. Payload shape: document_id, pipeline_status, event_type, occurred_at
  3. Skips events that have no document_id
  4. Handles redis.publish failure without crashing (logs, continues)
  5. Channel name matches SSE endpoint subscription key exactly
  6. No extra fields leaked into the published payload
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kafka.consumers.sse_fanout_consumer import SSEFanoutConsumer


def _make_consumer(redis_mock=None):
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    redis_mock = redis_mock or AsyncMock()
    redis_mock.publish = AsyncMock()

    with patch("kafka.consumers.sse_fanout_consumer.AIOKafkaConsumer"):
        consumer = SSEFanoutConsumer(settings=settings, redis=redis_mock)

    return consumer, redis_mock


def _make_kafka_message(event: dict):
    msg = MagicMock()
    msg.value = event
    return msg


# ── Channel naming ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publishes_to_correct_redis_channel():
    consumer, redis = _make_consumer()
    event = {
        "document_id":     "doc-abc-123",
        "pipeline_status": "EXTRACTING",
        "event_type":      "STAGE_CHANGED",
        "occurred_at":     "2026-06-19T10:00:00Z",
    }

    # Simulate one Kafka message flowing through the consumer logic
    msg = _make_kafka_message(event)
    consumer._consumer = AsyncMock()

    async def _one_message():
        yield msg

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start  = AsyncMock()
    consumer._consumer.stop   = AsyncMock()

    await consumer.run()

    redis.publish.assert_called_once()
    channel = redis.publish.call_args[0][0]
    assert channel == "sse:doc:doc-abc-123"


@pytest.mark.asyncio
async def test_channel_format_matches_sse_endpoint_subscription():
    """Channel key used by SSEFanoutConsumer must match what pipeline_status_stream subscribes to."""
    consumer, redis = _make_consumer()
    doc_id = "doc-xyz-789"
    event = {"document_id": doc_id, "pipeline_status": "ROUTED", "event_type": "STAGE_CHANGED", "occurred_at": "2026-06-19T11:00:00Z"}

    consumer._consumer = AsyncMock()

    async def _one_message():
        yield _make_kafka_message(event)

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    channel = redis.publish.call_args[0][0]
    # SSE endpoint subscribes to f"sse:doc:{document_id}" — must match exactly
    assert channel == f"sse:doc:{doc_id}"


# ── Payload shape ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_published_payload_contains_required_fields():
    consumer, redis = _make_consumer()
    event = {
        "document_id":     "doc-payload-001",
        "pipeline_status": "RESOLVING",
        "event_type":      "STAGE_CHANGED",
        "occurred_at":     "2026-06-19T12:00:00Z",
        "tenant_id":       "tenant-001",     # extra field — must NOT leak
        "actor_id":        "op-001",         # extra field — must NOT leak
    }

    consumer._consumer = AsyncMock()

    async def _one_message():
        yield _make_kafka_message(event)

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    raw_payload = redis.publish.call_args[0][1]
    payload = json.loads(raw_payload)

    assert payload["document_id"]     == "doc-payload-001"
    assert payload["pipeline_status"] == "RESOLVING"
    assert payload["event_type"]      == "STAGE_CHANGED"
    assert payload["occurred_at"]     == "2026-06-19T12:00:00Z"


@pytest.mark.asyncio
async def test_published_payload_does_not_leak_extra_fields():
    """tenant_id, actor_id, s3_key etc. must NOT appear in SSE payload — browser sees it."""
    consumer, redis = _make_consumer()
    event = {
        "document_id":     "doc-leak-002",
        "pipeline_status": "ROUTED",
        "event_type":      "STAGE_CHANGED",
        "occurred_at":     "2026-06-19T13:00:00Z",
        "tenant_id":       "t-secret",
        "actor_id":        "op-secret",
        "s3_key":          "staging/t-secret/doc-leak-002.pdf",
        "pan_token":       "should-never-appear",
    }

    consumer._consumer = AsyncMock()

    async def _one_message():
        yield _make_kafka_message(event)

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    raw_payload = redis.publish.call_args[0][1]
    payload = json.loads(raw_payload)

    assert "tenant_id"  not in payload
    assert "actor_id"   not in payload
    assert "s3_key"     not in payload
    assert "pan_token"  not in payload


# ── Missing document_id — skip ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skips_event_without_document_id():
    """Events missing document_id must be dropped — no publish."""
    consumer, redis = _make_consumer()
    bad_event = {
        "pipeline_status": "ROUTED",
        "event_type":      "STAGE_CHANGED",
        "occurred_at":     "2026-06-19T14:00:00Z",
        # no document_id
    }

    consumer._consumer = AsyncMock()

    async def _one_message():
        yield _make_kafka_message(bad_event)

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_skips_event_with_null_document_id():
    consumer, redis = _make_consumer()
    bad_event = {"document_id": None, "pipeline_status": "ROUTED", "event_type": "STAGE_CHANGED", "occurred_at": "2026-06-19T15:00:00Z"}

    consumer._consumer = AsyncMock()

    async def _one_message():
        yield _make_kafka_message(bad_event)

    consumer._consumer.__aiter__ = lambda _: _one_message()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    redis.publish.assert_not_called()


# ── Fault tolerance ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_continues_after_redis_publish_failure():
    """A Redis publish error must not crash the consumer — it logs and continues."""
    consumer, redis = _make_consumer()
    redis.publish = AsyncMock(side_effect=Exception("Redis connection lost"))

    event = {"document_id": "doc-fault-001", "pipeline_status": "EXTRACTING", "event_type": "STAGE_CHANGED", "occurred_at": "2026-06-19T16:00:00Z"}
    good_event = {"document_id": "doc-fault-002", "pipeline_status": "ROUTED", "event_type": "STAGE_CHANGED", "occurred_at": "2026-06-19T16:01:00Z"}

    consumer._consumer = AsyncMock()

    async def _two_messages():
        yield _make_kafka_message(event)
        yield _make_kafka_message(good_event)

    consumer._consumer.__aiter__ = lambda _: _two_messages()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    # Must not raise — consumer should survive the publish failure
    await consumer.run()

    # Both messages were attempted
    assert redis.publish.call_count == 2


@pytest.mark.asyncio
async def test_consumer_stops_on_exit():
    """Consumer.stop() must be called in the finally block even if iteration ends cleanly."""
    consumer, redis = _make_consumer()

    consumer._consumer = AsyncMock()

    async def _empty():
        return
        yield  # make it an async generator

    consumer._consumer.__aiter__ = lambda _: _empty()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    consumer._consumer.stop.assert_called_once()


# ── Multiple events ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publishes_one_event_per_kafka_message():
    consumer, redis = _make_consumer()
    events = [
        {"document_id": f"doc-multi-{i}", "pipeline_status": "EXTRACTING", "event_type": "STAGE_CHANGED", "occurred_at": "2026-06-19T17:00:00Z"}
        for i in range(5)
    ]

    consumer._consumer = AsyncMock()

    async def _five_messages():
        for e in events:
            yield _make_kafka_message(e)

    consumer._consumer.__aiter__ = lambda _: _five_messages()
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop  = AsyncMock()

    await consumer.run()

    assert redis.publish.call_count == 5
    channels = [call[0][0] for call in redis.publish.call_args_list]
    for i, ch in enumerate(channels):
        assert ch == f"sse:doc:doc-multi-{i}"
