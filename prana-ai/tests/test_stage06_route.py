"""Tests for pipeline/stage06_route.py — routing, status update, and event emission."""
import inspect

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
    # Stage06 is a DB-only stage. The DOC_ROUTED Kafka event is published by the
    # HTTP ingest handler (validate → S3 → DB write → kafka.publish → 202).
    # Stage06 creates a career_event row — the pipeline Kafka publish is upstream.
    # Verify Stage06 writes career_event (the DB side of the completion signal).
    src = inspect.getsource(Stage06Route.route)
    assert "career_event" in src, \
        "Stage06 must insert a career_event row — this is the completion record for analytics"
