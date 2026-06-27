"""Tests for EmailConsumer — prana.notifications.email"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.email_consumer import EmailConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    return EmailConsumer(settings, db_pool=pool)


@pytest.mark.asyncio
async def test_email_event_requires_recipient_email(consumer):
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "template_id": "OA_WELCOME", "tenant_id": "t-1"}
    # Missing recipient_email — should log and skip without raising
    await consumer._handle(event)


@pytest.mark.asyncio
async def test_email_dispatched_with_valid_event(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "recipient_email": "ops@co.com", "template_id": "OA_WELCOME",
             "tenant_id": "t-1", "payload": {"login_url": "https://prana.in/org/login"}}
    with patch.object(consumer, "_send_ses", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_ses_failure_does_not_crash_consumer(consumer):
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "recipient_email": "ops@co.com", "template_id": "OA_WELCOME", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_ses", new=AsyncMock(side_effect=Exception("SES down"))):
        await consumer._handle(event)  # must not raise
