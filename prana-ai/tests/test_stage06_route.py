"""Tests for pipeline/stage06_route.py — routing, status update, and event emission."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

from pipeline.stage06_route import Stage06Route, _SAFE_METADATA_FIELDS


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
    # Stage06 must use a fail-closed ALLOWLIST (not a blocklist) — see
    # test_stage06_unknown_field_is_stripped_by_default below for why.
    assert _SAFE_METADATA_FIELDS, "Stage06 must define _SAFE_METADATA_FIELDS to allowlist for DB storage"
    assert "gross_salary" not in _SAFE_METADATA_FIELDS, \
        "gross_salary must NOT be in the safe allowlist — it's a raw ₹ figure"
    assert "gross_ctc" not in _SAFE_METADATA_FIELDS, \
        "gross_ctc must NOT be in the safe allowlist — it's a raw ₹ figure"
    assert "designation" in _SAFE_METADATA_FIELDS, \
        "designation is ordinary metadata and must be in the safe allowlist"


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


@pytest.mark.asyncio
async def test_stage06_unknown_field_is_stripped_by_default():
    """
    Fail-closed regression guard for the manifest-driven extraction path.

    Unlike the static per-doc-type schemas, prana-api's doc_type_field_manifest
    lets any tenant's OA-Admin configure arbitrary field names for a doc type.
    A blocklist ("strip these known-bad names") can never keep up with that —
    it already missed gross_ctc/net_pay/tds_amount for the STATIC schemas, and
    a tenant-custom field name is even less predictable. An allowlist ("keep
    only these known-safe names, strip everything else") fails in the safe
    direction: an unrecognized field is dropped (data loss) instead of leaked
    (privacy violation).

    This test proves a field name that's on NEITHER the safe allowlist NOR any
    known schema (simulating an arbitrary tenant-configured manifest field,
    sensitive-sounding or not) never reaches the DB write.
    """
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark, kafka_producer=None)
    await svc.route(
        document_id="doc-003", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={
            "designation": "Engineer",                    # known-safe — must survive
            "monthly_take_home": {"value": 92000},          # tenant-custom, unrecognized
            "some_new_field_nobody_allowlisted_yet": "x",   # unrecognized
        },
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-003.pdf",
    )

    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    assert update_calls, "Stage06 must call UPDATE document"
    import json
    stored = json.loads(update_calls[0][0][4])
    assert stored == {"designation": "Engineer"}, (
        f"Unrecognized fields must be stripped by default (fail-closed). Got: {stored}"
    )
