"""Tests for WhatsAppConsumer — prana.notifications.whatsapp.

Now a real channel adapter: calls WhatsAppService.send() directly (real WABA
Meta Cloud API, vendor chain + circuit breaker) and writes notification_log
itself — no longer routes through NotificationService.notify() (which
stubbed WhatsApp entirely; this is the first real implementation). See
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=False)  # whatsapp_opt_out = False by default
    conn.fetch = AsyncMock(return_value=[])         # no DB-stored vendor credentials by default
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.whatsapp_consumer import WhatsAppConsumer
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        whatsapp_provider="waba",
    )
    pool, _ = db_pool
    return WhatsAppConsumer(settings, db_pool=pool, redis=MagicMock(), kms_service=MagicMock())


@pytest.mark.asyncio
async def test_whatsapp_sent_when_not_opted_out(consumer):
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1", "template_data": {}}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_whatsapp_blocked_when_opted_out(consumer, db_pool):
    _, conn = db_pool
    conn.fetchval.return_value = True  # whatsapp_opt_out = True
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-2", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock()) as mock_send:
        await consumer._handle(event)
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_whatsapp_failure_does_not_crash_consumer(consumer):
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-3", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1"}
    with patch.object(consumer, "_send_whatsapp", new=AsyncMock(side_effect=Exception("WABA down"))):
        await consumer._handle(event)  # must not raise


@pytest.mark.asyncio
async def test_send_whatsapp_calls_whatsapp_service(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.whatsapp_consumer.WhatsAppService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._send_whatsapp(event)
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "+919876543210"
    assert call_kwargs["body"] == "DOC_ROUTED"
    assert call_kwargs["tenant_id"] == "t-1"
    assert call_kwargs["template_params"] is None   # empty template_data -> no components


@pytest.mark.asyncio
async def test_send_whatsapp_passes_template_data_as_ordered_params(consumer, db_pool):
    """Regression: template_data was fetched but discarded — any WABA template
    with {{1}}/{{2}} placeholders sent with them unfilled. Values flow through
    in template_data's insertion order, same order-preserving convention
    _build_email_body already uses for email."""
    _, conn = db_pool
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1",
             "template_data": {"employee_name": "Priya", "doc_type": "Salary Slip"}}
    with patch("kafka.consumers.whatsapp_consumer.WhatsAppService.send",
               new=AsyncMock(return_value=(True, None))) as mock_send:
        await consumer._send_whatsapp(event)
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["template_params"] == ["Priya", "Salary Slip"]


@pytest.mark.asyncio
async def test_send_whatsapp_writes_notification_log(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1", "template_data": {}}
    with patch("kafka.consumers.whatsapp_consumer.WhatsAppService.send",
               new=AsyncMock(return_value=(True, None))):
        await consumer._send_whatsapp(event)
    conn.execute.assert_called_once()
    sql, *args = conn.execute.call_args[0]
    assert "notification_log" in sql
    assert "SENT" in args


@pytest.mark.asyncio
async def test_send_whatsapp_missing_phone_or_template_skips(consumer, db_pool):
    _, conn = db_pool
    with patch("kafka.consumers.whatsapp_consumer.WhatsAppService.send", new=AsyncMock()) as mock_send:
        await consumer._send_whatsapp({"event_type": "DOC_ROUTED", "tenant_id": "t-1"})
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_whatsapp_dispatch_uses_db_stored_credentials_when_present(consumer, db_pool):
    """A PA-entered credential must actually reach WhatsAppService, or editing
    via the PA screen would be cosmetic — see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1."""
    _, conn = db_pool
    conn.fetch.return_value = [{"field_name": "whatsapp_waba_token", "enc_value": "ciphertext-1"}]
    consumer._kms.decrypt_value = MagicMock(return_value="db-configured-waba-token")
    event = {"event_type": "DOC_ROUTED", "recipient_id": "u-1", "recipient_phone": "+919876543210",
             "template_id": "DOC_ROUTED", "tenant_id": "t-1", "template_data": {}}

    captured = {}
    def _capture_init(self, settings, config, breaker):
        captured["settings"] = settings
        self._settings = settings
        self._config = config
        self._breaker = breaker

    with patch("kafka.consumers.whatsapp_consumer.WhatsAppService.__init__", _capture_init), \
         patch("kafka.consumers.whatsapp_consumer.WhatsAppService.send", new=AsyncMock(return_value=(True, None))):
        await consumer._send_whatsapp(event)

    assert captured["settings"].whatsapp_waba_token == "db-configured-waba-token"
