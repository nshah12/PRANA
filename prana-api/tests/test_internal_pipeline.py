"""
Tests for /internal/pipeline/* endpoints.
These endpoints are only callable from prana-ai (X-Internal-Service header).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
    mock_kafka.stage_changed.assert_called_once_with(
        document_id="doc-1", tenant_id="t-1",
        stage="RESOLVING", status="IN_PROGRESS", detail=None,
    )


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
    mock_db.acquire = MagicMock(return_value=conn)
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
    mock_kafka.stage_changed.assert_called_once_with(
        document_id="doc-1", tenant_id="t-1",
        stage="EXCEPTION", status="FAILED", detail="UNRESOLVED",
    )
