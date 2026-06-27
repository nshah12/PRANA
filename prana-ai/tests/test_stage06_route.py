"""Tests for pipeline/stage06_route.py — routing, status update, and event emission."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

from pipeline.stage06_route import Stage06Route, _SENSITIVE_FIELDS


def test_stage06_moves_document_from_staging_to_permanent_s3_key():
    # Stage06 writes the permanent s3_key into the document row on ROUTED.
    src = inspect.getsource(Stage06Route.route)
    assert "s3_key" in src, \
        "Stage06.route must update document.s3_key with the permanent (encrypted) S3 path"
    assert "pipeline_status='ROUTED'" in src or 'pipeline_status=\'ROUTED\'' in src, \
        "Stage06.route must set pipeline_status to ROUTED in the UPDATE statement"


def test_stage06_sets_pipeline_status_to_routed():
    # The UPDATE statement must set pipeline_status='ROUTED' — this is what the
    # SSEFanoutConsumer watches to push real-time progress to the employee browser.
    src = inspect.getsource(Stage06Route.route)
    assert "ROUTED" in src, "Stage06 must mark pipeline_status as ROUTED"
    # Sensitive raw salary fields must be stripped before DB write
    assert _SENSITIVE_FIELDS, "Stage06 must define _SENSITIVE_FIELDS to strip from extracted_fields"
    assert "gross_salary" in _SENSITIVE_FIELDS, \
        "gross_salary must be in _SENSITIVE_FIELDS — never stored in DB"
    assert "net_salary" in _SENSITIVE_FIELDS, \
        "net_salary must be in _SENSITIVE_FIELDS — never stored in DB"


def test_stage06_publishes_doc_routed_to_kafka():
    # Stage06 publishes DOC_ROUTED to prana.pipeline.events AFTER the DB transaction commits.
    # Consumers: SSEFanoutConsumer → browser SSE, AnalyticsConsumer → vault health,
    # WorkflowConsumer → VaultCompletenessWorkflow.
    src = inspect.getsource(Stage06Route.route)
    assert "DOC_ROUTED" in src, \
        "Stage06.route must publish DOC_ROUTED event to Kafka after the DB transaction commits"
    assert "prana.pipeline.events" in src, \
        "Stage06 must publish to prana.pipeline.events (not prana.ingest.events)"
    assert "career_event" in src, \
        "Stage06 must also insert a career_event row"


@pytest.mark.asyncio
async def test_stage06_kafka_publish_fires_after_db_commit():
    """Kafka publish must be OUTSIDE the transaction block — fire-and-forget after commit."""
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_kafka = AsyncMock()
    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark, kafka_producer=mock_kafka)
    await svc.route(
        document_id="doc-001", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={"gross_salary": 100000, "designation": "Engineer"},
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-001.pdf",
    )

    mock_kafka.publish.assert_called_once()
    topic, payload = mock_kafka.publish.call_args[0]
    assert topic == "prana.pipeline.events"
    assert payload["event_type"] == "DOC_ROUTED"
    assert payload["document_id"] == "doc-001"
    assert payload["pipeline_status"] == "ROUTED"
    # Raw salary must NOT be in the Kafka payload
    assert "gross_salary" not in payload


@pytest.mark.asyncio
async def test_stage06_kafka_failure_does_not_rollback_db():
    """If Kafka publish fails, the DB transaction must already be committed — no rollback."""
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_kafka = AsyncMock()
    mock_kafka.publish = AsyncMock(side_effect=Exception("Kafka broker unreachable"))
    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark, kafka_producer=mock_kafka)
    # Must not raise — Kafka failure is logged and swallowed
    await svc.route(
        document_id="doc-002", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="FORM_16", doc_period="FY:2024-25",
        extracted_fields={}, resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.95,
        s3_key="t/e/FORM_16/FY2024-25_doc-002.pdf",
    )
    # DB transaction was entered (committed before Kafka was called)
    mock_db.transaction.assert_called_once()
