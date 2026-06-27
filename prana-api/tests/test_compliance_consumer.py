"""Tests for ComplianceConsumer — prana.compliance.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def temporal():
    t = AsyncMock()
    t.start_workflow = AsyncMock()
    return t


@pytest.fixture
def consumer(temporal):
    from kafka.consumers.compliance_consumer import ComplianceConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    c = ComplianceConsumer(settings, temporal_client=temporal)
    return c


@pytest.mark.asyncio
async def test_erasure_requested_starts_workflow(consumer, temporal):
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-1", "tenant_id": "t-1"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("ERASURE_REQUESTED", event)
    temporal.start_workflow.assert_awaited_once()
    call_kwargs = temporal.start_workflow.call_args
    assert call_kwargs[1]["id"] == "erasure-eu-1"
    assert call_kwargs[1]["task_queue"] == "prana-compliance"


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


@pytest.mark.asyncio
async def test_erasure_notifies_email_and_sms(consumer, temporal):
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-5", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ERASURE_REQUESTED", event)
    mock_kafka.notify_email.assert_awaited_once()
    mock_kafka.notify_sms.assert_awaited_once()


@pytest.mark.asyncio
async def test_already_running_workflow_is_idempotent(consumer, temporal):
    temporal.start_workflow.side_effect = Exception("Workflow with this ID already exists")
    event = {"event_type": "ERASURE_REQUESTED", "employee_user_id": "eu-6", "tenant_id": "t-1"}
    with patch("kafka.consumers.compliance_consumer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        await consumer._dispatch("ERASURE_REQUESTED", event)  # must not raise
