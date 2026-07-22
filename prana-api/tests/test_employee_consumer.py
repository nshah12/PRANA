"""Tests for EmployeeConsumer — prana.employee.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def consumer():
    from kafka.consumers.employee_consumer import EmployeeConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    temporal = AsyncMock()
    kafka_producer = AsyncMock()
    return EmployeeConsumer(settings, temporal_client=temporal, db_pool=MagicMock(), kafka_producer=kafka_producer)


@pytest.mark.asyncio
async def test_employee_onboarded_starts_no_workflow(consumer):
    """Regression guard: this used to start "IdentityResolutionWorkflow" — a
    workflow class never @workflow.defn'd anywhere in workflows/ nor registered
    in worker.py's WORKERS map. Against a real Temporal server that raises the
    first time EMPLOYEE_ONBOARDED fires; against the mocked client used in this
    test suite it silently "passed" (assert_awaited_once), which is exactly how
    it shipped unnoticed. Identity resolution actually happens per-document
    inside DocumentPipelineWorkflow's stage 05, so no employee-level workflow
    belongs here."""
    event = {"event_type": "EMPLOYEE_ONBOARDED", "tenant_id": "t-1",
             "employee_uuid": "em-1", "employment_type": "PERMANENT"}
    await consumer._dispatch("EMPLOYEE_ONBOARDED", event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_employee_rejoined_starts_rejoining_workflow(consumer):
    """EMPLOYEE_REJOINED must start RejoiningWorkflow (workflows/employee_lifecycle.py),
    which reconciles the existing vault and re-links via pan_token dedup — not the
    nonexistent "IdentityResolutionWorkflow" started here before."""
    event = {"event_type": "EMPLOYEE_REJOINED", "tenant_id": "t-1", "employee_uuid": "em-9"}
    await consumer._dispatch("EMPLOYEE_REJOINED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "RejoiningWorkflow"
    assert call.kwargs["id"] == "rejoin-em-9"
    # RejoiningWorkflow is registered on admin-queue in worker.py.
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_vault_activated_starts_workflow_on_admin_queue(consumer):
    """VaultActivationWorkflow is registered on admin-queue in worker.py, not
    prana-ingest — a wrong queue means the workflow starts but is never polled
    by any worker."""
    event = {"event_type": "VAULT_ACTIVATED", "tenant_id": "t-1", "employee_uuid": "em-3"}
    await consumer._dispatch("VAULT_ACTIVATED", event)
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "VaultActivationWorkflow"
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_employee_exited_starts_exit_workflow_on_admin_queue(consumer):
    """EmployeeExitWorkflow is registered on admin-queue in worker.py, not prana-admin."""
    event = {"event_type": "EMPLOYEE_EXITED", "tenant_id": "t-1",
             "employee_uuid": "em-2", "dol": "2026-06-01"}
    await consumer._dispatch("EMPLOYEE_EXITED", event)
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "EmployeeExitWorkflow"
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_account_dormant_starts_workflow_on_admin_queue(consumer):
    """AccountDormancyWorkflow is registered on admin-queue in worker.py, not prana-admin."""
    event = {"event_type": "ACCOUNT_DORMANT", "tenant_id": "t-1", "employee_user_id": "em-5"}
    await consumer._dispatch("ACCOUNT_DORMANT", event)
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "AccountDormancyWorkflow"
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_already_running_workflow_is_idempotent(consumer):
    consumer._temporal.start_workflow.side_effect = Exception("Workflow with this ID already exists")
    event = {"event_type": "VAULT_ACTIVATED", "tenant_id": "t-1", "employee_uuid": "em-6"}
    await consumer._dispatch("VAULT_ACTIVATED", event)  # must not raise


@pytest.mark.asyncio
async def test_unknown_event_does_not_raise(consumer):
    await consumer._dispatch("UNKNOWN_EVENT", {"tenant_id": "t-1"})
    consumer._temporal.start_workflow.assert_not_awaited()
