"""Tests for WhatsAppConsumer — prana.notifications.whatsapp"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=False)  # whatsapp_opt_out = False by default
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.whatsapp_consumer import WhatsAppConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    return WhatsAppConsumer(settings, db_pool=pool)


@pytest.mark.asyncio
async def test_whatsapp_sent_when_not_opted_out(consumer):
    event = {"event_type": "CONSENT_WITHDRAWN", "recipient_id": "u-1",
             "template_id": "CONSENT_WITHDRAWN", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_whatsapp_blocked_when_opted_out(consumer, db_pool):
    _, conn = db_pool
    conn.fetchval.return_value = True  # whatsapp_opt_out = True
    event = {"event_type": "CONSENT_WITHDRAWN", "recipient_id": "u-2",
             "template_id": "CONSENT_WITHDRAWN", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_whatsapp_failure_does_not_crash_consumer(consumer):
    event = {"event_type": "CONSENT_WITHDRAWN", "recipient_id": "u-3",
             "template_id": "CONSENT_WITHDRAWN", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock(side_effect=Exception("WABA down"))):
        await consumer._handle(event)  # must not raise
