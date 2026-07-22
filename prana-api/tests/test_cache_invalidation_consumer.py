"""
Tests for kafka/consumers/cache_invalidation_consumer.py.

Regression coverage for a confirmed wiring bug: the consumer subscribed to
"prana.cache.events" while kafka.producer.KafkaPub.cache_invalidate() only ever
publishes to TOPIC_CACHE_INVAL ("prana.cache.invalidation"). Every
CONFIG_INVALIDATE / APIKEY_INVALIDATE / MANIFEST_INVALIDATE /
EMPLOYEE_PROFILE_INVALIDATE / TENANT_INVALIDATE / OA_PERMISSIONS_INVALIDATE /
DROPDOWN_INVALIDATE / SESSION_INVALIDATE event was silently dropped — the
consumer listened on a topic nothing published to.
"""
from unittest.mock import MagicMock, patch

import pytest


def _make_consumer(redis=None):
    from config import Settings
    settings = MagicMock(spec=Settings)
    settings.kafka_bootstrap_servers = "localhost:9092"
    with patch("kafka.consumers.cache_invalidation_consumer.AIOKafkaConsumer") as mock_cls:
        from kafka.consumers.cache_invalidation_consumer import CacheInvalidationConsumer
        consumer = CacheInvalidationConsumer(settings, redis or MagicMock())
    return consumer, mock_cls


def test_subscribes_to_the_same_topic_producer_publishes_to():
    from kafka.producer import TOPIC_CACHE_INVAL
    consumer, mock_cls = _make_consumer()
    subscribed_topics = mock_cls.call_args.args
    assert TOPIC_CACHE_INVAL in subscribed_topics
    assert "prana.cache.events" not in subscribed_topics


@pytest.mark.asyncio
async def test_config_invalidate_dispatches_to_cache_service():
    from unittest.mock import AsyncMock
    consumer, _ = _make_consumer()
    consumer._cache = AsyncMock()
    await consumer._dispatch("CONFIG_INVALIDATE", {"tenant_id": "t-1", "config_key": "otp_ttl"})
    consumer._cache.invalidate_config.assert_awaited_once_with("t-1")
