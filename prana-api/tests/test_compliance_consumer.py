"""Tests for ComplianceConsumer — prana.compliance.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def temporal():
    t = AsyncMock()
    t.start_workflow = AsyncMock()
    return t


@pytest.fixture
def db_pool():
    """DPDP-mandated notifications (erasure, grievance, consent withdrawal) need
    a real recipient_email/recipient_phone looked up from employee_user — this
    consumer used to have no db_pool at all, so it never could."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="emp@example.com")
    conn.fetchrow = AsyncMock(return_value={"enc_mobile": "kms-ciphertext-blob"})
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def kms():
    k = MagicMock()
    k.decrypt_value = MagicMock(return_value="+919000000001")
    return k


@pytest.fixture
def consumer(temporal, db_pool, kms):
    from kafka.consumers.compliance_consumer import ComplianceConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    c = ComplianceConsumer(settings, temporal_client=temporal, db_pool=pool, kms_service=kms)
    return c


@pytest.mark.asyncio
async def test_erasure_requested_starts_workflow(consumer, temporal):
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-1", "tenant_id": "t-1"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("ERASURE_REQUESTED", event)
    temporal.start_workflow.assert_awaited_once()
    call_kwargs = temporal.start_workflow.call_args
    assert call_kwargs[1]["id"] == "erasure-eu-1"
    # ErasureConfirmationWorkflow is registered on compliance-queue in worker.py —
    # a wrong queue means the workflow starts but is never polled by any worker.
    assert call_kwargs[1]["task_queue"] == "compliance-queue"


@pytest.mark.asyncio
async def test_grievance_filed_starts_workflow(consumer, temporal):
    event = {"event_type": "GRIEVANCE_FILED", "employee_user_id": "eu-2",
             "grievance_id": "g-1", "tenant_id": "t-1"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("GRIEVANCE_FILED", event)
    temporal.start_workflow.assert_awaited_once()
    assert temporal.start_workflow.call_args[1]["id"] == "grievance-g-1"


@pytest.mark.asyncio
async def test_data_export_starts_workflow(consumer, temporal):
    event = {"event_type": "DATA_EXPORT_REQUESTED", "employee_user_id": "eu-3",
             "export_id": "ex-1", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("DATA_EXPORT_REQUESTED", event)
    temporal.start_workflow.assert_awaited_once()
    mock_kafka.notify_push.assert_awaited_once()


@pytest.mark.asyncio
async def test_consent_withdrawn_notifies_whatsapp(consumer, temporal):
    event = {"event_type": "CONSENT_WITHDRAWN", "employee_user_id": "eu-4",
             "tenant_id": "t-1", "purpose": "notifications"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("CONSENT_WITHDRAWN", event)
    mock_kafka.notify_whatsapp.assert_awaited_once()
    notif = mock_kafka.notify_whatsapp.call_args[0][0]
    assert notif["event_type"] == "CONSENT_WITHDRAWN"
    # Regression: WhatsAppConsumer requires recipient_phone or it silently skips —
    # this consumer used to never resolve it (no db_pool/kms at all).
    assert notif["recipient_phone"] == "+919000000001"
    assert notif["template_data"]["purpose"] == "notifications"
    assert "payload" not in notif


@pytest.mark.asyncio
async def test_consent_withdrawn_does_not_start_a_temporal_workflow(consumer, temporal):
    """
    Consent withdrawal is a DPDP-mandated IMMEDIATE action (no grace period) —
    the consent_status DB write already happens synchronously in the HTTP handler
    (routers/compliance.py::withdraw_consent, routers/dpdp.py::withdraw_consent_purpose)
    before this Kafka event is even published. There is no durable-timer/signal
    need here (unlike ErasureConfirmationWorkflow's 30-day cooling-off), so no
    Temporal workflow should be started for this event — only the notification.

    Regression test for a bug where the consumer called
    self._temporal.start_workflow("ConsentWithdrawalWorkflow", ...) — a workflow
    name never defined anywhere in workflows/compliance.py nor documented in
    workflows/CLAUDE.md's DPDP & Legal Compliance domain. Against a real Temporal
    server this raises (unregistered workflow type) the first time a
    CONSENT_WITHDRAWN event fires; against the mocked client in the other test
    above it silently "passes", which is exactly why it shipped unnoticed.
    """
    event = {"event_type": "CONSENT_WITHDRAWN", "employee_user_id": "eu-7",
             "tenant_id": "t-1", "purpose": "notifications"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("CONSENT_WITHDRAWN", event)
    temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_erasure_notifies_email_and_sms(consumer, temporal):
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-5", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ERASURE_REQUESTED", event)
    mock_kafka.notify_email.assert_awaited_once()
    mock_kafka.notify_sms.assert_awaited_once()
    # Regression: DPDP mandates this erasure confirmation actually reach the
    # employee — EmailConsumer/SMSConsumer silently skip without
    # recipient_email/recipient_phone, and this consumer used to never resolve
    # either (no db_pool at all, and content was under a dead "payload" key).
    email_notif = mock_kafka.notify_email.call_args[0][0]
    sms_notif = mock_kafka.notify_sms.call_args[0][0]
    assert email_notif["recipient_email"] == "emp@example.com"
    assert email_notif["template_data"]["cancel_before_days"] == 30
    assert sms_notif["recipient_phone"] == "+919000000001"
    assert sms_notif["template_data"]["cancel_before_days"] == 30


@pytest.mark.asyncio
async def test_grievance_filed_notifies_email_with_recipient(consumer, temporal):
    event = {"event_type": "GRIEVANCE_FILED", "employee_user_id": "eu-9",
             "grievance_id": "g-2", "tenant_id": "t-1", "subject": "Wrong designation"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("GRIEVANCE_FILED", event)
    mock_kafka.notify_email.assert_awaited_once()
    notif = mock_kafka.notify_email.call_args[0][0]
    assert notif["recipient_email"] == "emp@example.com"
    assert notif["template_data"]["subject"] == "Wrong designation"


@pytest.mark.asyncio
async def test_notify_email_skips_recipient_lookup_gracefully_when_employee_not_found(consumer, temporal, db_pool):
    """If the employee_user row is gone (e.g. already erased), the notify call
    must still go out — just without recipient_email — rather than crash. The
    channel consumer's own missing-recipient warning/skip is the correct place
    for this to end, matching every other consumer's best-effort pattern."""
    _, conn = db_pool
    conn.fetchval = AsyncMock(return_value=None)
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-gone", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ERASURE_REQUESTED", event)  # must not raise
    mock_kafka.notify_email.assert_awaited_once()
    assert "recipient_email" not in mock_kafka.notify_email.call_args[0][0]


@pytest.mark.asyncio
async def test_data_correction_requested_starts_workflow(consumer, temporal):
    event = {"event_type": "DATA_CORRECTION_REQUESTED", "employee_user_id": "eu-8",
             "correction_id": "cor-1", "tenant_id": "t-1", "field": "designation"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("DATA_CORRECTION_REQUESTED", event)
    temporal.start_workflow.assert_awaited_once()
    assert temporal.start_workflow.call_args[1]["id"] == "correction-cor-1"
    assert temporal.start_workflow.call_args[1]["task_queue"] == "compliance-queue"


@pytest.mark.asyncio
async def test_already_running_workflow_is_idempotent(consumer, temporal):
    temporal.start_workflow.side_effect = Exception("Workflow with this ID already exists")
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-6", "tenant_id": "t-1"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("ERASURE_REQUESTED", event)  # must not raise
