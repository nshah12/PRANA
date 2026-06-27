"""Tests for StatutoryConsumer — prana.statutory.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch.return_value = [{"oa_user_id": "u-chro"}, {"oa_user_id": "u-cfo"}]
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.statutory_consumer import StatutoryConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return StatutoryConsumer(settings, db_pool=pool, temporal_client=temporal)


@pytest.mark.asyncio
async def test_obligation_due_notifies_chro_and_cfo_via_bell(consumer, db_pool):
    event = {"event_type": "OBLIGATION_DUE", "tenant_id": "t-1",
             "obligation_id": "ob-1", "act": "EPF_ACT", "due_date": "2026-07-15"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.statutory_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("OBLIGATION_DUE", event)
    assert mock_kafka.notify_bell.await_count == 2  # CHRO + CFO


@pytest.mark.asyncio
async def test_obligation_overdue_starts_escalation_workflow(consumer):
    event = {"event_type": "OBLIGATION_OVERDUE", "tenant_id": "t-1", "obligation_id": "ob-2"}
    await consumer._dispatch("OBLIGATION_OVERDUE", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    assert "ob-2" in consumer._temporal.start_workflow.call_args[1]["id"]


@pytest.mark.asyncio
async def test_gratuity_eligibility_starts_workflow(consumer):
    event = {"event_type": "GRATUITY_ELIGIBILITY_TRIGGERED", "tenant_id": "t-1",
             "employee_uuid": "em-1"}
    await consumer._dispatch("GRATUITY_ELIGIBILITY_TRIGGERED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_bell_notification_has_correct_payload(consumer, db_pool):
    event = {"event_type": "OBLIGATION_DUE", "tenant_id": "t-1",
             "obligation_id": "ob-3", "act": "ESIC_ACT", "due_date": "2026-08-01"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.statutory_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("OBLIGATION_DUE", event)
    notif = mock_kafka.notify_bell.call_args[0][0]
    assert notif["template_id"] == "OBLIGATION_DUE"
    assert notif["payload"]["act"] == "ESIC_ACT"
