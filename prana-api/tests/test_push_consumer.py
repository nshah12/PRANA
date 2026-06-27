"""Tests for PushConsumer — prana.notifications.push"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def consumer():
    from kafka.consumers.push_consumer import PushConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    return PushConsumer(settings, db_pool=MagicMock())


@pytest.mark.asyncio
async def test_push_dispatched_with_valid_event(consumer):
    event = {"event_type": "DATA_EXPORT_REQUESTED", "recipient_id": "u-1",
             "template_id": "DATA_EXPORT_REQUESTED", "tenant_id": "t-1",
             "payload": {"message": "Your data export is being prepared"}}
    with patch.object(consumer, "_send_push", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_requires_recipient_id(consumer):
    event = {"event_type": "DATA_EXPORT_REQUESTED", "template_id": "DATA_EXPORT_REQUESTED",
             "tenant_id": "t-1"}
    with patch.object(consumer, "_send_push", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_failure_does_not_crash_consumer(consumer):
    event = {"event_type": "DATA_EXPORT_REQUESTED", "recipient_id": "u-1",
             "template_id": "DATA_EXPORT_REQUESTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_push", new=AsyncMock(side_effect=Exception("FCM down"))):
        await consumer._handle(event)  # must not raise
