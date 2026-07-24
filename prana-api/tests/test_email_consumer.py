"""Tests for EmailConsumer — prana.notifications.email.

Now a real channel adapter: calls EmailService.send_email() directly (vendor
chain + circuit breaker) and writes notification_log itself — no longer
routes through NotificationService.notify() (prana-docs/
COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4).
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
    from kafka.consumers.email_consumer import EmailConsumer
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        email_provider="ses",
    )
    pool, _ = db_pool
    return EmailConsumer(settings, db_pool=pool, redis=MagicMock(), kms_service=MagicMock())


@pytest.mark.asyncio
async def test_email_event_requires_recipient_email(consumer):
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "template_id": "OA_WELCOME", "tenant_id": "t-1"}
    await consumer._handle(event)   # missing recipient_email — logs and skips, no raise


@pytest.mark.asyncio
async def test_email_dispatched_calls_email_service_send(consumer, db_pool):
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "recipient_email": "ops@co.com", "template_id": "OA_WELCOME",
             "tenant_id": "t-1", "template_data": {"login_url": "https://prana.in/org/login"}}
    with patch("kafka.consumers.email_consumer.EmailService.send_email",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._handle(event)
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "ops@co.com"
    assert call_kwargs["tenant_id"] == "t-1"


@pytest.mark.asyncio
async def test_email_dispatched_writes_notification_log(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "recipient_email": "ops@co.com", "template_id": "OA_WELCOME",
             "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.email_consumer.EmailService.send_email",
               new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)
    conn.execute.assert_called_once()
    sql, *args = conn.execute.call_args[0]
    assert "notification_log" in sql
    assert "SENT" in args


@pytest.mark.asyncio
async def test_email_send_failure_logs_failed_status_not_raise(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
             "recipient_email": "ops@co.com", "template_id": "OA_WELCOME", "tenant_id": "t-1"}
    with patch("kafka.consumers.email_consumer.EmailService.send_email",
               new=AsyncMock(return_value=(False, "all email vendors in chain exhausted"))):
        await consumer._handle(event)   # must not raise
    sql, *args = conn.execute.call_args[0]
    assert "FAILED" in args
    assert "all email vendors in chain exhausted" in args


@pytest.mark.asyncio
async def test_email_dispatch_uses_db_stored_credentials_when_present(consumer, db_pool):
    """A PA-entered credential (services/communication_settings_service.py's
    get_effective_settings) must actually reach EmailService, or editing via
    the PA screen would be cosmetic — see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1."""
    _, conn = db_pool
    conn.fetch.return_value = [{"field_name": "smtp_host", "enc_value": "ciphertext-1"}]
    consumer._kms.decrypt_value = MagicMock(return_value="db-configured-smtp.example.com")
    event = {"event_type": "OA_WELCOME", "recipient_id": "u-1",
              "recipient_email": "ops@co.com", "template_id": "OA_WELCOME",
              "tenant_id": "t-1", "template_data": {}}

    captured = {}
    def _capture_init(self, settings, config, breaker):
        captured["settings"] = settings
        self._settings = settings
        self._config = config
        self._breaker = breaker
        self._provider = settings.email_provider

    with patch("kafka.consumers.email_consumer.EmailService.__init__", _capture_init), \
         patch("kafka.consumers.email_consumer.EmailService.send_email",
               new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)

    assert captured["settings"].smtp_host == "db-configured-smtp.example.com"
