"""Tests for SMSConsumer — prana.notifications.sms.

Now a real channel adapter: calls SMSService.send() directly (vendor chain +
circuit breaker) and writes notification_log itself — no longer routes
through NotificationService.notify() (which stubbed SMS entirely). See
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4.
"""
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
    from kafka.consumers.sms_consumer import SMSConsumer
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        sms_provider="aws",
    )
    pool, _ = db_pool
    return SMSConsumer(settings, db_pool=pool, redis=MagicMock(), kms_service=MagicMock())


@pytest.mark.asyncio
async def test_sms_dispatched_with_phone(consumer):
    event = {"event_type": "VAULT_WELCOME", "recipient_id": "u-1",
             "recipient_phone": "+919876543210", "template_id": "VAULT_WELCOME",
             "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.sms_consumer.SMSService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._handle(event)
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "+919876543210"
    assert call_kwargs["tenant_id"] == "t-1"


@pytest.mark.asyncio
async def test_sms_skipped_without_phone(consumer):
    event = {"event_type": "VAULT_WELCOME", "recipient_id": "u-2",
             "template_id": "VAULT_WELCOME", "tenant_id": "t-1"}
    with patch("kafka.consumers.sms_consumer.SMSService.send", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_phone_masked_in_logs(consumer):
    """Phone number must never appear in plain text in logs."""
    event = {"event_type": "VAULT_WELCOME", "recipient_phone": "+919876543210",
             "template_id": "VAULT_WELCOME", "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.sms_consumer.SMSService.send", new=AsyncMock(return_value=(True, None))):
        import logging
        with patch.object(logging.getLogger("kafka.consumers.sms_consumer"), "info") as mock_log:
            await consumer._handle(event)
            for call in mock_log.call_args_list:
                assert "+919876543210" not in str(call), "Full phone number leaked into logs"


@pytest.mark.asyncio
async def test_sms_dispatched_writes_notification_log(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "VAULT_WELCOME", "recipient_id": "u-1",
             "recipient_phone": "+919876543210", "template_id": "VAULT_WELCOME",
             "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.sms_consumer.SMSService.send", new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)
    conn.execute.assert_called_once()
    sql, *args = conn.execute.call_args[0]
    assert "notification_log" in sql
    assert "SENT" in args


@pytest.mark.asyncio
async def test_sms_send_failure_logs_failed_status_not_raise(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "VAULT_WELCOME", "recipient_id": "u-1",
             "recipient_phone": "+919876543210", "template_id": "VAULT_WELCOME", "tenant_id": "t-1"}
    with patch("kafka.consumers.sms_consumer.SMSService.send",
               new=AsyncMock(return_value=(False, "all sms vendors in chain exhausted"))):
        await consumer._handle(event)   # must not raise
    sql, *args = conn.execute.call_args[0]
    assert "FAILED" in args


@pytest.mark.asyncio
async def test_sms_dispatch_uses_db_stored_credentials_when_present(consumer, db_pool):
    """A PA-entered credential must actually reach SMSService, or editing via
    the PA screen would be cosmetic — see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1."""
    _, conn = db_pool
    conn.fetch.return_value = [{"field_name": "exotel_api_key", "enc_value": "ciphertext-1"}]
    consumer._kms.decrypt_value = MagicMock(return_value="db-configured-exotel-key")
    event = {"event_type": "VAULT_WELCOME", "recipient_id": "u-1",
             "recipient_phone": "+919876543210", "template_id": "VAULT_WELCOME",
             "tenant_id": "t-1", "template_data": {}}

    captured = {}
    def _capture_init(self, settings, config, breaker):
        captured["settings"] = settings
        self._settings = settings
        self._config = config
        self._breaker = breaker
        self._provider = settings.sms_provider

    with patch("kafka.consumers.sms_consumer.SMSService.__init__", _capture_init), \
         patch("kafka.consumers.sms_consumer.SMSService.send", new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)

    assert captured["settings"].exotel_api_key == "db-configured-exotel-key"
