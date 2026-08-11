"""Tests for PushConsumer — prana.notifications.push

Real channel adapter (2026-08-06 — was the last consumer still on the
pre-Communication-Hub NotificationService.notify() stub; every other channel
consumer was upgraded during the Hub build). Calls PushService.send()
directly (vendor chain + circuit breaker) and writes notification_log
itself, fanning out to every registered device.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.push_consumer import PushConsumer
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        push_provider="dev",
    )
    pool, _ = db_pool
    return PushConsumer(settings, db_pool=pool, redis=MagicMock())


@pytest.mark.asyncio
async def test_push_dispatched_with_valid_event(consumer):
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_push", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_blocks_dispatch_when_template_data_contains_pan(consumer, db_pool):
    """Privacy guard added 2026-08-10 — see test_email_consumer.py's equivalent test
    for the full rationale."""
    pool, conn = db_pool
    conn.fetch = AsyncMock(return_value=[
        {"device_credential_id": "dev-1", "push_token": "expo-token-1"},
    ])
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1",
             "template_data": {"pan": "ABCDE1234F"}}
    with patch("kafka.consumers.push_consumer.PushService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._handle(event)
    mock_send.assert_not_awaited()
    conn.execute.assert_called_once()
    sql, *args = conn.execute.call_args[0]
    assert "notification_log" in sql
    assert "BLOCKED" in args


@pytest.mark.asyncio
async def test_push_requires_recipient_id(consumer):
    event = {"event_type": "DOC_ROUTED", "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_push", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_failure_does_not_crash_consumer(consumer):
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_push", new=AsyncMock(side_effect=Exception("Expo down"))):
        await consumer._handle(event)  # must not raise


@pytest.mark.asyncio
async def test_send_push_skips_when_no_registered_device(consumer, db_pool):
    _, conn = db_pool
    conn.fetch.return_value = []
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch("kafka.consumers.push_consumer.PushService.send", new=AsyncMock()) as mock_send:
        await consumer._send_push("u-1", "DOC_ROUTED", event)
    mock_send.assert_not_awaited()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_send_push_dispatches_to_every_registered_device(consumer, db_pool):
    _, conn = db_pool
    conn.fetch.return_value = [
        {"device_credential_id": "dev-1", "push_token": "ExponentPushToken[a]"},
        {"device_credential_id": "dev-2", "push_token": "ExponentPushToken[b]"},
    ]
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch("kafka.consumers.push_consumer.PushService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._send_push("u-1", "DOC_ROUTED", event)
    assert mock_send.await_count == 2
    tokens_sent = {c.kwargs["to"] for c in mock_send.call_args_list}
    assert tokens_sent == {"ExponentPushToken[a]", "ExponentPushToken[b]"}


@pytest.mark.asyncio
async def test_send_push_writes_notification_log_sent_when_any_device_succeeds(consumer, db_pool):
    _, conn = db_pool
    conn.fetch.return_value = [{"device_credential_id": "dev-1", "push_token": "ExponentPushToken[a]"}]
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch("kafka.consumers.push_consumer.PushService.send",
               new=AsyncMock(return_value=(True, None))):
        await consumer._send_push("u-1", "DOC_ROUTED", event)
    log_call = next(c for c in conn.execute.call_args_list if "notification_log" in c.args[0])
    assert "SENT" in log_call.args


@pytest.mark.asyncio
async def test_send_push_clears_dead_token_on_device_not_registered(consumer, db_pool):
    _, conn = db_pool
    conn.fetch.return_value = [{"device_credential_id": "dev-dead", "push_token": "ExponentPushToken[dead]"}]
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch("kafka.consumers.push_consumer.PushService.send",
               new=AsyncMock(return_value=(False, "DeviceNotRegistered"))):
        await consumer._send_push("u-1", "DOC_ROUTED", event)
    clear_call = next(c for c in conn.execute.call_args_list if "push_token=NULL" in c.args[0])
    assert clear_call.args[1] == "dev-dead"


@pytest.mark.asyncio
async def test_send_push_missing_recipient_or_template_skips(consumer, db_pool):
    _, conn = db_pool
    with patch("kafka.consumers.push_consumer.PushService.send", new=AsyncMock()) as mock_send:
        await consumer._handle({"event_type": "DOC_ROUTED", "tenant_id": "t-1"})
    mock_send.assert_not_awaited()
