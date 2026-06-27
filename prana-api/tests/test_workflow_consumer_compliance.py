"""
Tests for WorkflowConsumer compliance event routing.

Verifies that ERASURE_REQUESTED, DATA_EXPORT_REQUESTED, GRIEVANCE_FILED,
and DATA_CORRECTION_REQUESTED events from prana.ingest.events each start
the correct Temporal workflow with the correct workflow ID and payload.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


def _make_consumer(temporal_client, db_pool=None):
    from config import Settings
    settings = MagicMock(spec=Settings)
    settings.kafka_bootstrap_servers = "localhost:9092"
    with patch("kafka.consumers.workflow_consumer.AIOKafkaConsumer"):
        from kafka.consumers.workflow_consumer import WorkflowConsumer
        consumer = WorkflowConsumer(settings, temporal_client, db_pool)
    return consumer


@pytest.fixture
def temporal():
    t = AsyncMock()
    # start_workflow returns a handle by default
    t.start_workflow = AsyncMock(return_value=MagicMock())
    return t


# ── ERASURE_REQUESTED ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_erasure_requested_starts_erasure_confirmation_workflow(temporal):
    consumer = _make_consumer(temporal)
    await consumer._handle_erasure_requested({
        "event_type": "ERASURE_REQUESTED",
        "employee_user_id": "emp-001",
        "tenant_id": "tenant-001",
        "erasure_id": "era-abc",
        "reason": "No longer wish to use PRANA",
    })
    temporal.start_workflow.assert_called_once()
    call_kwargs = temporal.start_workflow.call_args
    # First arg is the workflow run method
    from workflows.compliance import ErasureConfirmationWorkflow
    assert call_kwargs[0][0] == ErasureConfirmationWorkflow.run
    assert call_kwargs[1]["id"] == "erasure-emp-001"
    assert call_kwargs[1]["task_queue"] == "compliance-queue"
    payload = call_kwargs[0][1]
    assert payload["employee_user_id"] == "emp-001"
    assert payload["erasure_id"] == "era-abc"


@pytest.mark.asyncio
async def test_erasure_requested_workflow_id_from_event(temporal):
    """If event carries an explicit workflow_id, use it (idempotency key from dpdp.py)."""
    consumer = _make_consumer(temporal)
    await consumer._handle_erasure_requested({
        "event_type": "ERASURE_REQUESTED",
        "employee_user_id": "emp-002",
        "workflow_id": "erasure-emp-002",
    })
    wf_id = temporal.start_workflow.call_args[1]["id"]
    assert wf_id == "erasure-emp-002"


@pytest.mark.asyncio
async def test_erasure_requested_already_running_is_safe(temporal):
    """WorkflowAlreadyStarted must not propagate — erasure is idempotent."""
    temporal.start_workflow.side_effect = Exception("Workflow already started")
    consumer = _make_consumer(temporal)
    # Should not raise
    await consumer._handle_erasure_requested({
        "event_type": "ERASURE_REQUESTED",
        "employee_user_id": "emp-001",
    })


# ── DATA_EXPORT_REQUESTED ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_export_requested_starts_data_export_workflow(temporal):
    consumer = _make_consumer(temporal)
    await consumer._handle_data_export_requested({
        "event_type": "DATA_EXPORT_REQUESTED",
        "employee_user_id": "emp-003",
        "tenant_id": "tenant-001",
        "export_id": "exp-xyz",
        "workflow_id": "export-emp-003-exp-xyz",
    })
    temporal.start_workflow.assert_called_once()
    from workflows.compliance import DataExportWorkflow
    assert temporal.start_workflow.call_args[0][0] == DataExportWorkflow.run
    assert temporal.start_workflow.call_args[1]["id"] == "export-emp-003-exp-xyz"
    assert temporal.start_workflow.call_args[1]["task_queue"] == "compliance-queue"
    payload = temporal.start_workflow.call_args[0][1]
    assert payload["export_id"] == "exp-xyz"


@pytest.mark.asyncio
async def test_data_export_each_request_gets_own_workflow(temporal):
    """Two export requests for same employee → two different workflow IDs."""
    consumer = _make_consumer(temporal)
    await consumer._handle_data_export_requested({
        "employee_user_id": "emp-003",
        "export_id": "exp-001",
        "workflow_id": "export-emp-003-exp-001",
    })
    await consumer._handle_data_export_requested({
        "employee_user_id": "emp-003",
        "export_id": "exp-002",
        "workflow_id": "export-emp-003-exp-002",
    })
    ids = [c[1]["id"] for c in temporal.start_workflow.call_args_list]
    assert ids[0] != ids[1], "Each export request must get its own workflow ID"


# ── GRIEVANCE_FILED ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grievance_filed_starts_grievance_workflow(temporal):
    consumer = _make_consumer(temporal)
    await consumer._handle_grievance_filed({
        "event_type": "GRIEVANCE_FILED",
        "grievance_id": "grv-001",
        "employee_user_id": "emp-004",
        "tenant_id": "tenant-001",
        "category": "DATA_ACCURACY",
        "description": "My designation is wrong",
        "workflow_id": "grievance-grv-001",
    })
    temporal.start_workflow.assert_called_once()
    from workflows.compliance import GrievanceWorkflow
    assert temporal.start_workflow.call_args[0][0] == GrievanceWorkflow.run
    assert temporal.start_workflow.call_args[1]["id"] == "grievance-grv-001"
    assert temporal.start_workflow.call_args[1]["task_queue"] == "compliance-queue"
    payload = temporal.start_workflow.call_args[0][1]
    assert payload["grievance_id"] == "grv-001"
    assert payload["category"] == "DATA_ACCURACY"


@pytest.mark.asyncio
async def test_grievance_workflow_id_deterministic_on_grievance_id(temporal):
    """Same grievance_id → same workflow ID → Temporal deduplicates."""
    consumer = _make_consumer(temporal)
    await consumer._handle_grievance_filed({
        "grievance_id": "grv-999",
        "employee_user_id": "emp-004",
    })
    wf_id = temporal.start_workflow.call_args[1]["id"]
    assert "grv-999" in wf_id


# ── DATA_CORRECTION_REQUESTED ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_correction_requested_starts_correction_workflow(temporal):
    consumer = _make_consumer(temporal)
    await consumer._handle_data_correction_requested({
        "event_type": "DATA_CORRECTION_REQUESTED",
        "correction_id": "cor-001",
        "employee_user_id": "emp-005",
        "tenant_id": "tenant-001",
        "field": "designation",
        "correct_value": "Senior Engineer",
    })
    temporal.start_workflow.assert_called_once()
    from workflows.compliance import DataCorrectionWorkflow
    assert temporal.start_workflow.call_args[0][0] == DataCorrectionWorkflow.run
    assert temporal.start_workflow.call_args[1]["id"] == "correction-cor-001"
    assert temporal.start_workflow.call_args[1]["task_queue"] == "compliance-queue"
    payload = temporal.start_workflow.call_args[0][1]
    assert payload["correction_id"] == "cor-001"
    assert payload["field"] == "designation"
    assert payload["correct_value"] == "Senior Engineer"


# ── run() routing dispatch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_routes_erasure_event_to_handler(temporal):
    """Integration: run() dispatches ERASURE_REQUESTED to _handle_erasure_requested."""
    consumer = _make_consumer(temporal)
    consumer._handle_erasure_requested = AsyncMock()
    consumer._handle_data_export_requested = AsyncMock()

    event = {
        "event_type": "ERASURE_REQUESTED",
        "employee_user_id": "emp-001",
    }

    # Simulate one message then stop
    async def _one_message(self_inner):
        yield MagicMock(value=event)
    consumer._consumer.__aiter__ = _one_message
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop = AsyncMock()

    await consumer.run()
    consumer._handle_erasure_requested.assert_called_once_with(event)
    consumer._handle_data_export_requested.assert_not_called()


@pytest.mark.asyncio
async def test_run_unknown_event_type_is_logged_not_raised(temporal):
    """Unknown event types must not crash the consumer loop."""
    consumer = _make_consumer(temporal)
    event = {"event_type": "UNKNOWN_FUTURE_EVENT", "data": "x"}

    async def _one_message(self_inner):
        yield MagicMock(value=event)
    consumer._consumer.__aiter__ = _one_message
    consumer._consumer.start = AsyncMock()
    consumer._consumer.stop = AsyncMock()

    # Must not raise
    await consumer.run()


# ── Contract tests ────────────────────────────────────────────────────────────

def test_all_compliance_workflows_on_compliance_queue():
    """All 4 DPDP workflows must use COMPLIANCE_TASK_QUEUE, not ingestsvc-queue."""
    from kafka.consumers.workflow_consumer import COMPLIANCE_TASK_QUEUE
    assert COMPLIANCE_TASK_QUEUE == "compliance-queue"


def test_statutory_compliance_workflow_registered_in_worker():
    import importlib
    worker = importlib.import_module("workflows.worker")
    queue_cfg = worker.WORKERS.get("compliance-queue", {})
    wf_names = [w.__name__ for w in queue_cfg.get("workflows", [])]
    assert "StatutoryComplianceWorkflow" in wf_names, \
        "StatutoryComplianceWorkflow must be registered in compliance-queue"


def test_compliance_activities_registered_in_worker():
    import importlib
    worker = importlib.import_module("workflows.worker")
    queue_cfg = worker.WORKERS.get("compliance-queue", {})
    act_names = {a.__name__ for a in queue_cfg.get("activities", [])}
    assert "mark_overdue_obligations" in act_names
    assert "notify_overdue_obligations" in act_names


# ── DOC_RECLASSIFIED — pool injection ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_doc_reclassified_uses_injected_pool_not_raw_connect(temporal):
    """_handle_doc_reclassified must use db_pool.acquire(), not asyncpg.connect()."""
    import inspect
    from kafka.consumers.workflow_consumer import WorkflowConsumer
    src = inspect.getsource(WorkflowConsumer._handle_doc_reclassified)
    assert "asyncpg.connect" not in src, \
        "_handle_doc_reclassified must use self._db_pool.acquire(), not raw asyncpg.connect()"
    assert "_db_pool" in src, \
        "_handle_doc_reclassified must use the injected pool"


@pytest.mark.asyncio
async def test_doc_reclassified_starts_pipeline_workflow(temporal):
    """DOC_RECLASSIFIED must restart DocumentPipelineWorkflow with resolved doc_type."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "s3_key": "tenant/emp/SALARY_SLIP/2025-05_doc-001.pdf",
        "s3_bucket": "prana-docs",
    })
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    consumer = _make_consumer(temporal, mock_pool)
    await consumer._handle_doc_reclassified({
        "event_type": "DOC_RECLASSIFIED",
        "document_id": "doc-001",
        "tenant_id": "tenant-001",
        "doc_type": "SALARY_SLIP",
        "run_attempt": 2,
    })

    temporal.start_workflow.assert_called_once()
    from workflows.document_pipeline import DocumentPipelineWorkflow
    assert temporal.start_workflow.call_args[0][0] == DocumentPipelineWorkflow.run
    wf_id = temporal.start_workflow.call_args[1]["id"]
    assert "doc-001" in wf_id
    assert "reclassified" in wf_id
    payload = temporal.start_workflow.call_args[0][1]
    assert payload["doc_type"] == "SALARY_SLIP"
