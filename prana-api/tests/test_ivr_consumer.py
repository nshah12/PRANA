"""Tests for IVRConsumer — prana.notifications.ivr (new).

Same shape as SMSConsumer/EmailConsumer: calls IVRService.send() directly
(Exotel/Ozonetel, vendor chain + circuit breaker) and writes
notification_log itself. See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])   # no DB-stored vendor credentials by default
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.ivr_consumer import IVRConsumer
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        ivr_provider="exotel",
    )
    pool, _ = db_pool
    return IVRConsumer(settings, db_pool=pool, redis=MagicMock(), kms_service=MagicMock())


@pytest.mark.asyncio
async def test_ivr_event_requires_phone_and_template(consumer):
    event = {"event_type": "ANOMALY_P0_ALERT", "recipient_id": "ciso-1", "template_id": "ANOMALY_P0_ALERT"}
    await consumer._handle(event)   # missing recipient_phone — logs and skips, no raise


@pytest.mark.asyncio
async def test_ivr_dispatched_calls_ivr_service_send(consumer):
    event = {"event_type": "ANOMALY_P0_ALERT", "recipient_id": "ciso-1",
             "recipient_phone": "+919876543210", "template_id": "ANOMALY_P0_ALERT",
             "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.ivr_consumer.IVRService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._handle(event)
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "+919876543210"
    assert call_kwargs["tenant_id"] == "t-1"


@pytest.mark.asyncio
async def test_ivr_dispatched_writes_notification_log(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "ANOMALY_P0_ALERT", "recipient_id": "ciso-1",
             "recipient_phone": "+919876543210", "template_id": "ANOMALY_P0_ALERT",
             "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.ivr_consumer.IVRService.send",
               new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)
    conn.execute.assert_called_once()
    sql, *args = conn.execute.call_args[0]
    assert "notification_log" in sql
    assert "SENT" in args


@pytest.mark.asyncio
async def test_ivr_send_failure_logs_failed_status_not_raise(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "ANOMALY_P0_ALERT", "recipient_id": "ciso-1",
             "recipient_phone": "+919876543210", "template_id": "ANOMALY_P0_ALERT", "tenant_id": "t-1"}
    with patch("kafka.consumers.ivr_consumer.IVRService.send",
               new=AsyncMock(return_value=(False, "all ivr vendors in chain exhausted"))):
        await consumer._handle(event)   # must not raise
    sql, *args = conn.execute.call_args[0]
    assert "FAILED" in args


@pytest.mark.asyncio
async def test_ivr_dispatch_uses_db_stored_credentials_when_present(consumer, db_pool):
    """A PA-entered credential must actually reach IVRService, or editing via
    the PA screen would be cosmetic — see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1."""
    _, conn = db_pool
    conn.fetch.return_value = [{"field_name": "ozonetel_api_key", "enc_value": "ciphertext-1"}]
    consumer._kms.decrypt_value = MagicMock(return_value="db-configured-ozonetel-key")
    event = {"event_type": "ANOMALY_P0_ALERT", "recipient_id": "ciso-1",
             "recipient_phone": "+919876543210", "template_id": "ANOMALY_P0_ALERT",
             "tenant_id": "t-1", "template_data": {}}

    captured = {}
    def _capture_init(self, settings, config, breaker):
        captured["settings"] = settings
        self._settings = settings
        self._config = config
        self._breaker = breaker

    with patch("kafka.consumers.ivr_consumer.IVRService.__init__", _capture_init), \
         patch("kafka.consumers.ivr_consumer.IVRService.send", new=AsyncMock(return_value=(True, None))):
        await consumer._handle(event)

    assert captured["settings"].ozonetel_api_key == "db-configured-ozonetel-key"
