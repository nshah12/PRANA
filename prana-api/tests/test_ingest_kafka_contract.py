"""
Kafka contract tests for the ingest HTTP handler.

Verifies the HTTP handler contract:
  validate → S3 put → 1 DB write → 1 Kafka publish → return 202

Must NEVER:
  - Write to audit_event in the HTTP path
  - Start Temporal workflows in the HTTP path
  - Send notifications in the HTTP path
"""
import base64
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


_MINIMAL_PDF = base64.b64encode(b"%PDF-1.4 fake content").decode()
_UPLOAD_PAYLOAD = {
    "tenant_id": "tenant-uuid-001",
    "doc_type": "SALARY_SLIP",
    "doc_period": "2024-03",
    "file_b64": _MINIMAL_PDF,
    "file_ext": "pdf",
}


def _make_tenant_row():
    return {
        "tenant_id": "tenant-uuid-001",
        "kek_arn": "arn:aws:kms:ap-south-1:123:key/abc",
        "push_window_months": 6,
        "status": "ACTIVE",
        "nik_type": "PAN",
    }


@pytest.mark.asyncio
async def test_ingest_publishes_exactly_one_kafka_event(client, mock_db, mock_kafka):
    """HTTP handler must publish exactly one DOC_INGESTED event and nothing else."""
    mock_db.fetchrow.return_value = _make_tenant_row()
    mock_db.fetchval.return_value = "doc-uuid-001"

    # Mock S3 upload
    client.app.state.s3 = MagicMock()
    client.app.state.s3.upload = MagicMock()

    with patch("routers.ingest._require_api_key") as mock_auth:
        mock_auth.return_value = MagicMock(tenant_id="tenant-uuid-001")
        resp = await client.post(
            "/ingest/document",
            json=_UPLOAD_PAYLOAD,
            headers={"X-PRANA-Key-ID": "test-key", "X-PRANA-Signature": "sig"},
        )

    # Must be 202 Accepted
    assert resp.status_code == 202

    # Exactly ONE Kafka publish (DOC_INGESTED to prana.ingest.events)
    assert mock_kafka.publish.call_count == 1
    topic, event = mock_kafka.publish.call_args[0]
    assert topic == "prana.ingest.events"
    assert event["event_type"] == "DOC_INGESTED"
    assert "document_id" in event


@pytest.mark.asyncio
async def test_ingest_does_not_write_audit_event_in_http_path(client, mock_db, mock_kafka):
    """AuditConsumer writes audit rows — the HTTP handler must not."""
    mock_db.fetchrow.return_value = _make_tenant_row()
    mock_db.fetchval.return_value = "doc-uuid-002"
    client.app.state.s3 = MagicMock()

    with patch("routers.ingest._require_api_key") as mock_auth:
        mock_auth.return_value = MagicMock(tenant_id="tenant-uuid-001")
        await client.post(
            "/ingest/document",
            json=_UPLOAD_PAYLOAD,
            headers={"X-PRANA-Key-ID": "test-key", "X-PRANA-Signature": "sig"},
        )

    # Scan all DB execute calls — none should touch audit_event
    for c in mock_db.execute.call_args_list:
        sql = str(c).lower()
        assert "audit_event" not in sql, f"HTTP path wrote audit_event: {c}"


@pytest.mark.asyncio
async def test_ingest_does_not_start_temporal_workflow(client, mock_db, mock_kafka):
    """WorkflowConsumer starts workflows — the HTTP handler must not."""
    mock_db.fetchrow.return_value = _make_tenant_row()
    mock_db.fetchval.return_value = "doc-uuid-003"
    client.app.state.s3 = MagicMock()
    temporal_mock = MagicMock()
    client.app.state.temporal_client = temporal_mock

    with patch("routers.ingest._require_api_key") as mock_auth:
        mock_auth.return_value = MagicMock(tenant_id="tenant-uuid-001")
        await client.post(
            "/ingest/document",
            json=_UPLOAD_PAYLOAD,
            headers={"X-PRANA-Key-ID": "test-key", "X-PRANA-Signature": "sig"},
        )

    temporal_mock.start_workflow.assert_not_called()
