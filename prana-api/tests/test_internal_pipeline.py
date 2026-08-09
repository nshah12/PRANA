"""
Tests for /internal/pipeline/* endpoints.
These endpoints are only callable from prana-ai (X-Internal-Service header).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from kafka.producer import KafkaPub


@pytest.fixture
def client(mock_db, mock_redis, mock_kafka):
    from fastapi.testclient import TestClient
    from main import create_app
    app = create_app()
    with TestClient(app) as c:
        # Re-set after lifespan runs (lifespan overwrites state with real infrastructure)
        app.state.db_pool = mock_db
        app.state.redis = mock_redis
        app.state.kafka_producer = mock_kafka
        yield c


INTERNAL_HEADERS = {"X-Internal-Service": "prana-ai"}


@pytest.fixture
def real_kafka_client(mock_db):
    """A real KafkaPub instance — `__new__` skips `__init__` (no AIOKafkaProducer
    construction, which needs a running event loop) — with only `publish` mocked
    out. mock_kafka's bare AsyncMock() accepts any kwargs silently, which is
    exactly why the doc_routed/stage_changed kwargs-vs-dict signature mismatch
    below went undetected — this fixture exercises the real domain-helper method
    signatures (stage_changed/doc_routed/etc., which all call self.publish)
    instead."""
    from fastapi.testclient import TestClient
    from main import create_app

    kafka = KafkaPub.__new__(KafkaPub)
    kafka.publish = AsyncMock()
    kafka.stop = AsyncMock()   # lifespan shutdown calls .stop(); __new__ skipped
                               # __init__ so there's no real self._producer to stop

    app = create_app()
    with TestClient(app) as c:
        app.state.db_pool = mock_db
        app.state.kafka_producer = kafka
        yield c, kafka


# ── Auth guard ────────────────────────────────────────────────────────────────

def test_stage_update_rejects_missing_header(client):
    resp = client.post("/internal/pipeline/stage", json={
        "document_id": "doc-1", "tenant_id": "t-1",
        "stage": "EXTRACTING", "status": "IN_PROGRESS",
    })
    assert resp.status_code == 403


def test_stage_update_rejects_wrong_service(client):
    resp = client.post("/internal/pipeline/stage",
                       headers={"X-Internal-Service": "prana-ask"},
                       json={
                           "document_id": "doc-1", "tenant_id": "t-1",
                           "stage": "EXTRACTING", "status": "IN_PROGRESS",
                       })
    assert resp.status_code == 403


# ── Stage update ──────────────────────────────────────────────────────────────

def test_stage_update_publishes_stage_changed(client, mock_kafka):
    mock_kafka.stage_changed = AsyncMock()
    resp = client.post("/internal/pipeline/stage",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id": "doc-1", "tenant_id": "t-1",
                           "stage": "RESOLVING", "status": "IN_PROGRESS",
                       })
    assert resp.status_code == 200
    mock_kafka.stage_changed.assert_called_once_with({
        "event_type":      "STAGE_CHANGED",
        "document_id":     "doc-1", "tenant_id": "t-1",
        "pipeline_status": "RESOLVING",
        "stage":           "RESOLVING", "status": "IN_PROGRESS", "detail": None,
    })


def test_stage_update_tolerates_kafka_failure(client, mock_kafka):
    mock_kafka.stage_changed = AsyncMock(side_effect=Exception("kafka down"))
    resp = client.post("/internal/pipeline/stage",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id": "doc-1", "tenant_id": "t-1",
                           "stage": "EXTRACTING", "status": "FAILED",
                       })
    # Must still return 200 — Kafka failure must not fail the callback
    assert resp.status_code == 200


# ── Routed callback ───────────────────────────────────────────────────────────

def test_routed_updates_db_and_publishes(client, mock_db, mock_kafka):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    # async with db.acquire() as conn — needs async context manager
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "t-1",
                           "employee_uuid":        "emp-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                       })
    assert resp.status_code == 200
    conn.execute.assert_called_once()
    mock_kafka.doc_routed.assert_called_once()


def test_routed_bumps_manifest_usage_count(client, mock_db, mock_kafka):
    """
    A successful route is a strong signal the AUTO_DETECT classification was
    correct — /internal/pipeline/routed must bump doc_type_field_manifest.usage_count
    so future AUTO_DETECT tie-breaking favors doc_types this tenant actually uses.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value="manifest-1")
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "11111111-1111-1111-1111-111111111111",
                           "employee_uuid":        "emp-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                       })
    assert resp.status_code == 200
    conn.fetchval.assert_called_once()
    query = conn.fetchval.call_args[0][0]
    assert "usage_count = usage_count + 1" in query
    assert conn.fetchval.call_args[0][1:] == (
        UUID("11111111-1111-1111-1111-111111111111"), "SALARY_SLIP",
    )


def test_routed_tolerates_manifest_usage_bump_failure(client, mock_db, mock_kafka):
    """A manifest usage_count bump failure must never fail the routed callback."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=Exception("db down"))
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "11111111-1111-1111-1111-111111111111",
                           "employee_uuid":        "emp-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                       })
    assert resp.status_code == 200
    mock_kafka.doc_routed.assert_called_once()


def test_routed_publishes_vault_activated_on_first_activation(client, mock_db, mock_kafka):
    """
    is_first_activation=True means this is the employee's first-ever routed
    document — VaultActivationWorkflow (employee_consumer.py's VAULT_ACTIVATED
    case) provisions the vault and sends the welcome notification, but nothing
    published this event before this fix.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock()
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()
    mock_kafka.employee_event = AsyncMock()

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "t-1",
                           "employee_uuid":        "emp-1",
                           "employee_user_id":     "emp-user-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                           "is_first_activation":  True,
                       })
    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once_with({
        "event_type":       "VAULT_ACTIVATED",
        "employee_uuid":    "emp-1",
        "employee_user_id": "emp-user-1",
        "tenant_id":        "t-1",
    })


def test_routed_skips_vault_activated_when_not_first(client, mock_db, mock_kafka):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()
    mock_kafka.employee_event = AsyncMock()

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-2",
                           "tenant_id":            "t-1",
                           "employee_uuid":        "emp-1",
                           "employee_user_id":     "emp-user-1",
                           "pan_token":            "abc123",
                           "doc_type":             "FORM_16",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                           "is_first_activation":  False,
                       })
    assert resp.status_code == 200
    mock_kafka.employee_event.assert_not_called()


def test_routed_vault_activated_failure_does_not_fail_callback(client, mock_db, mock_kafka):
    """A VAULT_ACTIVATED publish failure must never fail the routed callback —
    DOC_ROUTED (already published) must not be rolled back by this."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    mock_kafka.doc_routed = AsyncMock()
    mock_kafka.employee_event = AsyncMock(side_effect=Exception("kafka down"))

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "t-1",
                           "employee_uuid":        "emp-1",
                           "employee_user_id":     "emp-user-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                           "is_first_activation":  True,
                       })
    assert resp.status_code == 200
    mock_kafka.doc_routed.assert_called_once()


def test_routed_rejects_without_header(client):
    resp = client.post("/internal/pipeline/routed", json={
        "document_id": "doc-1", "tenant_id": "t-1",
        "employee_uuid": "emp-1", "pan_token": "x",
        "doc_type": "SALARY_SLIP",
        "resolution_method": "PAN_EXACT", "resolution_confidence": 0.99,
    })
    assert resp.status_code == 403


# ── Exception callback ────────────────────────────────────────────────────────

def test_exception_publishes_stage_changed(client, mock_kafka):
    mock_kafka.stage_changed = AsyncMock()
    resp = client.post("/internal/pipeline/exception",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":    "doc-1",
                           "tenant_id":      "t-1",
                           "exception_type": "UNRESOLVED",
                       })
    assert resp.status_code == 200
    mock_kafka.stage_changed.assert_called_once_with({
        "event_type":      "STAGE_CHANGED",
        "document_id":     "doc-1", "tenant_id": "t-1",
        "pipeline_status": "EXCEPTION",
        "stage":           "EXCEPTION", "status": "FAILED", "detail": "UNRESOLVED",
    })


# ── Real KafkaPub signature regression (found via live verification 2026-08-07) ─
#
# KafkaPub.stage_changed/doc_routed/employee_event (kafka/producer.py) all take
# exactly one positional `event: dict` argument. Every call site above passes
# kwargs instead (document_id=..., tenant_id=..., ...) — that binds fine against
# mock_kafka (a bare AsyncMock() with no signature to violate) but raises
# TypeError against the real KafkaPub, and the try/except Exception around every
# call site swallows it silently, logs, and still returns 200. This meant
# DOC_ROUTED — the event every downstream consumer (SSEFanoutConsumer,
# AnalyticsConsumer, WorkflowConsumer's gamification refresh, CommunicationHub's
# DOC_ROUTED notification) depends on — never actually reached Kafka in any real
# deployment. Caught only by exercising the real KafkaPub.doc_routed/stage_changed
# signature, not by the mocked tests above.

def test_stage_update_real_kafka_signature_does_not_raise(real_kafka_client):
    client, kafka = real_kafka_client
    resp = client.post("/internal/pipeline/stage",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id": "doc-1", "tenant_id": "t-1",
                           "stage": "RESOLVING", "status": "IN_PROGRESS",
                       })
    assert resp.status_code == 200
    kafka.publish.assert_awaited()
    event = kafka.publish.call_args_list[0].args[1]
    assert event["event_type"] == "STAGE_CHANGED"
    assert event["document_id"] == "doc-1"
    assert event["pipeline_status"] == "RESOLVING"


def test_routed_real_kafka_signature_does_not_raise(real_kafka_client, mock_db):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=acquire_ctx)
    client, kafka = real_kafka_client

    resp = client.post("/internal/pipeline/routed",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":          "doc-1",
                           "tenant_id":            "t-1",
                           "employee_uuid":        "emp-1",
                           "employee_user_id":     "person-1",
                           "pan_token":            "abc123",
                           "doc_type":             "SALARY_SLIP",
                           "resolution_method":    "PAN_EXACT",
                           "resolution_confidence": 0.99,
                       })
    assert resp.status_code == 200
    kafka.publish.assert_awaited()
    doc_routed_calls = [c for c in kafka.publish.call_args_list
                        if c.args[1].get("event_type") == "DOC_ROUTED"]
    assert len(doc_routed_calls) >= 1
    event = doc_routed_calls[0].args[1]
    assert event["document_id"] == "doc-1"
    assert event["tenant_id"] == "t-1"
    assert event["employee_uuid"] == "emp-1"
    assert event["employee_user_id"] == "person-1"  # needed by WorkflowConsumer + CommunicationHubConsumer
    assert event["pipeline_status"] == "ROUTED"


def test_exception_real_kafka_signature_does_not_raise(real_kafka_client):
    client, kafka = real_kafka_client
    resp = client.post("/internal/pipeline/exception",
                       headers=INTERNAL_HEADERS,
                       json={
                           "document_id":    "doc-1",
                           "tenant_id":      "t-1",
                           "exception_type": "UNRESOLVED",
                       })
    assert resp.status_code == 200
    kafka.publish.assert_awaited()
    event = kafka.publish.call_args_list[0].args[1]
    assert event["event_type"] == "STAGE_CHANGED"
    assert event["pipeline_status"] == "EXCEPTION"
