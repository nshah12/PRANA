"""Tests for OAUserConsumer — prana.oa_users.events"""
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
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return OAUserConsumer(settings, db_pool=pool, temporal_client=temporal)


@pytest.mark.asyncio
async def test_oa_user_created_publishes_welcome_email(consumer):
    event = {"event_type": "OA_USER_CREATED", "oa_user_id": "u-1",
             "email": "ops@co.com", "tenant_id": "t-1", "role": "oa_operator"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("OA_USER_CREATED", event)
    mock_kafka.notify_email.assert_awaited_once()
    notif = mock_kafka.notify_email.call_args[0][0]
    assert notif["template_id"] == "OA_WELCOME"
    assert notif["recipient_id"] == "u-1"


@pytest.mark.asyncio
async def test_oa_user_locked_starts_account_lock_workflow(consumer):
    event = {"event_type": "OA_USER_LOCKED", "oa_user_id": "u-2", "tenant_id": "t-1"}
    await consumer._dispatch("OA_USER_LOCKED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    assert consumer._temporal.start_workflow.call_args[1]["id"] == "account-lock-oa-u-2"


@pytest.mark.asyncio
async def test_elevation_approved_sends_email(consumer):
    event = {"event_type": "ELEVATION_APPROVED", "oa_user_id": "u-3",
             "requestor_id": "u-3", "elevation_id": "e-1", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ELEVATION_APPROVED", event)
    mock_kafka.notify_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_elevation_expired_sends_bell_not_email(consumer):
    event = {"event_type": "ELEVATION_EXPIRED", "oa_user_id": "u-4",
             "requestor_id": "u-4", "elevation_id": "e-2", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ELEVATION_EXPIRED", event)
    mock_kafka.notify_bell.assert_awaited_once()
    mock_kafka.notify_email.assert_not_awaited()
