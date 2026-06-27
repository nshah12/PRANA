"""Tests for SMSConsumer — prana.notifications.sms"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def consumer():
    from kafka.consumers.sms_consumer import SMSConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    return SMSConsumer(settings, db_pool=MagicMock())


@pytest.mark.asyncio
async def test_sms_dispatched_with_phone(consumer):
    event = {"event_type": "ERASURE_REQUESTED", "recipient_id": "u-1",
             "recipient_phone": "+919876543210", "template_id": "ERASURE_REQUESTED",
             "tenant_id": "t-1"}
    with patch.object(consumer, "_send_sms", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_sms_skipped_without_phone(consumer):
    event = {"event_type": "ERASURE_REQUESTED", "recipient_id": "u-2",
             "template_id": "ERASURE_REQUESTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_sms", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_phone_masked_in_logs(consumer):
    """Phone number must never appear in plain text in logs."""
    event = {"event_type": "ERASURE_REQUESTED", "recipient_phone": "+919876543210",
             "template_id": "ERASURE_REQUESTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_sms", new=AsyncMock()):
        import logging
        with patch.object(logging.getLogger("kafka.consumers.sms_consumer"), "info") as mock_log:
            await consumer._handle(event)
            for call in mock_log.call_args_list:
                log_msg = str(call)
                assert "+919876543210" not in log_msg, "Full phone number leaked into logs"
