"""Tests for EmployeeConsumer — prana.employee.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def consumer():
    from kafka.consumers.employee_consumer import EmployeeConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    temporal = AsyncMock()
    kafka_producer = AsyncMock()
    return EmployeeConsumer(settings, temporal_client=temporal, db_pool=MagicMock(), kafka_producer=kafka_producer)


@pytest.mark.asyncio
async def test_employee_onboarded_starts_identity_resolution(consumer):
    event = {"event_type": "EMPLOYEE_ONBOARDED", "tenant_id": "t-1",
             "employee_uuid": "em-1", "employment_type": "PERMANENT"}
    await consumer._dispatch("EMPLOYEE_ONBOARDED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    assert "identity" in consumer._temporal.start_workflow.call_args[1]["id"].lower() or \
           "employee" in consumer._temporal.start_workflow.call_args[1]["id"].lower()


@pytest.mark.asyncio
async def test_employee_exited_starts_exit_workflow(consumer):
    event = {"event_type": "EMPLOYEE_EXITED", "tenant_id": "t-1",
             "employee_uuid": "em-2", "dol": "2026-06-01"}
    await consumer._dispatch("EMPLOYEE_EXITED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_event_does_not_raise(consumer):
    await consumer._dispatch("UNKNOWN_EVENT", {"tenant_id": "t-1"})
    consumer._temporal.start_workflow.assert_not_awaited()
