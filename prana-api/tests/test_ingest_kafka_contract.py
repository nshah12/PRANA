"""
Kafka contract tests for the ingest HTTP handler.

Verifies the HTTP handler contract:
  validate → S3 put → 1 DB write → 1 Kafka publish → return 202

Must NEVER:
  - Write to audit_event in the HTTP path
  - Start Temporal workflows in the HTTP path (except ElevationWorkflow via direct start — see kafka02-correlated-start-ok marker)
  - Send notifications in the HTTP path

The /upload endpoint uses multipart form data (UploadFile), not JSON.
Auth: OAOperator dependency — bypassed via jwt_service mock (same pattern as test_chro.py).
"""
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}

_MINIMAL_PDF_BYTES = b"%PDF-1.4 fake content"


def _set_auth(client, role: str = "oa_operator", tenant_id: str = "tenant-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "op-uuid-001",
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _make_upload_files():
    """Multipart files dict for httpx test client."""
    return [("files", ("slip_apr.pdf", io.BytesIO(_MINIMAL_PDF_BYTES), "application/pdf"))]


# ── Auth guard ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_requires_auth(client, mock_db, mock_kafka):
    """Unauthenticated ingest must be rejected before any DB or S3 work."""
    resp = await client.post(
        "/v1/ingest/upload",
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_rejects_cfo_role(client, mock_db, mock_kafka):
    """CFO cannot upload — only oa_operator / oa_admin."""
    _set_auth(client, role="cfo")
    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP"},
    )
    assert resp.status_code == 403


# ── Kafka contract ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_publishes_exactly_one_kafka_event(client, mock_db, mock_kafka):
    """Single-file upload must publish exactly one DOC_INGESTED event."""
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-001")

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP", "doc_period": "2024-03"},
    )

    assert resp.status_code == 202

    # Exactly ONE DOC_INGESTED publish (no audit, no workflow, no notification)
    assert mock_kafka.doc_ingested.call_count == 1
    event = mock_kafka.doc_ingested.call_args[0][0]
    assert event["event_type"] == "DOC_INGESTED"
    assert "document_id" in event
    assert event["tenant_id"] == "tenant-uuid-001"


@pytest.mark.asyncio
async def test_ingest_does_not_write_audit_event_in_http_path(client, mock_db, mock_kafka):
    """AuditConsumer writes audit rows — the HTTP handler must not."""
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-002")

    await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP"},
    )

    for c in mock_db.execute.call_args_list:
        sql = str(c).lower()
        assert "audit_event" not in sql, f"HTTP path wrote audit_event: {c}"


@pytest.mark.asyncio
async def test_ingest_does_not_start_temporal_workflow(client, mock_db, mock_kafka):
    """WorkflowConsumer starts document workflows — the HTTP handler must not."""
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-003")

    temporal_mock = MagicMock()
    temporal_mock.start_workflow = AsyncMock()
    client.app.state.temporal_client = temporal_mock

    await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP"},
    )

    # No document pipeline workflow start in HTTP path
    for call in temporal_mock.start_workflow.call_args_list:
        workflow_arg = str(call)
        assert "DocumentPipeline" not in workflow_arg, \
            f"HTTP path started Temporal workflow: {call}"


@pytest.mark.asyncio
async def test_ingest_returns_202_immediately(client, mock_db, mock_kafka):
    """Handler must return 202 Accepted, not 200 or 201."""
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-004")

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "FORM_16"},
    )

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_ingest_rejects_non_pdf(client, mock_db, mock_kafka):
    """Non-PDF files must be rejected before S3/DB/Kafka."""
    _set_auth(client)

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=[("files", ("slip.exe", io.BytesIO(b"binary"), "application/octet-stream"))],
        data={"doc_type": "SALARY_SLIP"},
    )

    # Should reject at validation — no Kafka publish for bad file
    if resp.status_code == 202:
        # File was rejected in results array — Kafka must NOT have been called
        data = resp.json()
        file_result = data if "error" in data else (data.get("files") or [data])[0]
        assert "error" in file_result
        assert mock_kafka.doc_ingested.call_count == 0


@pytest.mark.asyncio
async def test_ingest_response_shape(client, mock_db, mock_kafka):
    """Single-file response must include document_id and pipeline_status."""
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-005")

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "OFFER_LETTER"},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert "document_id" in data
    assert data.get("pipeline_status") == "QUEUED"


# ── SSE contract ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_endpoint_subscribes_to_redis_not_db(client, mock_db, mock_redis):
    """SSE pipeline status stream must use Redis Pub/Sub, never poll the DB."""
    _set_auth(client)

    # DB: document ownership check (one fetchrow) — then no more DB calls
    mock_db.fetchrow = AsyncMock(return_value={"pipeline_status": "EXTRACTING"})

    pubsub_mock = MagicMock()
    pubsub_mock.subscribe = AsyncMock()
    pubsub_mock.unsubscribe = AsyncMock()
    pubsub_mock.close = AsyncMock()

    async def _mock_listen():
        yield {"type": "subscribe", "data": 1}
        yield {"type": "message", "data": '{"pipeline_status":"ROUTED"}'}

    pubsub_mock.listen = _mock_listen
    mock_redis.pubsub = MagicMock(return_value=pubsub_mock)

    resp = await client.get(
        "/v1/ingest/status/doc-uuid-001",
        headers={**AUTH_HEADER, "Accept": "text/event-stream"},
    )

    # SSE endpoint opened — Redis pubsub was used
    assert resp.status_code == 200
    pubsub_mock.subscribe.assert_called_once()
    subscribed_channel = pubsub_mock.subscribe.call_args[0][0]
    assert subscribed_channel == "sse:doc:doc-uuid-001"

    # Verify DB was only queried once (ownership check) — not polled in a loop
    assert mock_db.fetchrow.call_count == 1
