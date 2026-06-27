"""
Tests for SSE pipeline status stream — GET /v1/ingest/status/{document_id}

Architecture under test:
  Browser → GET /ingest/status/{doc_id}
    → verify tenant ownership (DB)
    → yield current pipeline_status immediately
    → subscribe to Redis Pub/Sub sse:doc:{doc_id}
    → yield each stage-change event until terminal state or 6-min timeout
    → SSEFanoutConsumer is the publisher (tested separately in test_sse_fanout_consumer.py)

Never polls YugabyteDB in the stream loop — Redis Pub/Sub only.
"""
import json
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_oa_auth(client, tenant_id="tenant-001"):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-001",
        "user_type": "oa_user",
        "role": "oa_operator",
        "tenant_id": tenant_id,
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _make_pubsub(*messages):
    """
    Build a mock Redis pubsub that yields a fixed sequence of messages then stops.
    Each item in `messages` is a dict with 'type' and 'data'.
    """
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()

    async def _listen():
        for msg in messages:
            yield msg
    pubsub.listen = _listen
    return pubsub


def _pipeline_message(status: str, doc_id: str = "doc-001") -> dict:
    return {
        "type": "message",
        "data": json.dumps({"document_id": doc_id, "pipeline_status": status}),
    }


def _subscribe_message() -> dict:
    return {"type": "subscribe", "data": 1}


# ── Auth boundary ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_requires_auth(client):
    resp = await client.get("/v1/ingest/status/doc-001")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_sse_employee_cannot_access(client):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "emp-001", "user_type": "employee", "role": "employee",
        "tenant_id": "tenant-001", "jti": "s1",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_returns_404_for_wrong_tenant(client, mock_db, mock_redis):
    _set_oa_auth(client, tenant_id="tenant-002")
    mock_db.fetchrow.return_value = None   # document doesn't belong to tenant-002
    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_sse_tenant_id_used_in_db_ownership_check(client, mock_db, mock_redis):
    """DB query must include tenant_id — never return docs across tenants."""
    _set_oa_auth(client, tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"pipeline_status": "ROUTED"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)

    query = mock_db.fetchrow.call_args[0][0]
    assert "tenant_id" in query, "DB query must filter by tenant_id"


# ── Terminal state — immediate return ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_already_routed_returns_immediately(client, mock_db, mock_redis):
    """ROUTED doc: emit one event with current status, don't open Redis subscription."""
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "ROUTED"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "ROUTED" in body
    # No Redis subscription opened for already-terminal docs
    pubsub.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_sse_already_exception_returns_immediately(client, mock_db, mock_redis):
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "EXCEPTION"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "EXCEPTION" in resp.text
    pubsub.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_sse_already_quarantined_returns_immediately(client, mock_db, mock_redis):
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "QUARANTINED"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert "QUARANTINED" in resp.text
    pubsub.subscribe.assert_not_called()


# ── In-progress doc — Redis subscription ─────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_in_progress_subscribes_to_correct_channel(client, mock_db, mock_redis):
    """In-progress doc must subscribe to sse:doc:{document_id}."""
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "EXTRACTING"}
    pubsub = _make_pubsub(
        _subscribe_message(),
        _pipeline_message("ROUTED"),   # terminal → stream ends
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)

    assert resp.status_code == 200
    pubsub.subscribe.assert_called_once_with("sse:doc:doc-001")


@pytest.mark.asyncio
async def test_sse_emits_initial_status_then_updates(client, mock_db, mock_redis):
    """First SSE frame = current DB status. Subsequent frames = Redis messages."""
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "ENCRYPTING"}
    pubsub = _make_pubsub(
        _subscribe_message(),
        _pipeline_message("SCANNING"),
        _pipeline_message("EXTRACTING"),
        _pipeline_message("ROUTED"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)

    body = resp.text
    assert "ENCRYPTING" in body    # initial state from DB
    assert "SCANNING" in body
    assert "EXTRACTING" in body
    assert "ROUTED" in body


@pytest.mark.asyncio
async def test_sse_stops_at_routed_terminal_state(client, mock_db, mock_redis):
    """Stream must close after ROUTED — not continue listening for more events."""
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "RESOLVING"}
    pubsub = _make_pubsub(
        _subscribe_message(),
        _pipeline_message("ROUTED"),
        # These should NOT appear — stream must have closed
        _pipeline_message("EXTRACTING"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    body = resp.text

    assert "ROUTED" in body
    # After ROUTED the generator must have exited — EXTRACTING must not appear
    # Count occurrences: only one pipeline_status block after ROUTED
    routed_idx = body.index("ROUTED")
    assert "EXTRACTING" not in body[routed_idx:], \
        "Stream must not emit events after terminal ROUTED state"


@pytest.mark.asyncio
async def test_sse_unsubscribes_on_completion(client, mock_db, mock_redis):
    """pubsub.unsubscribe and pubsub.close must be called — no resource leak."""
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "SCANNING"}
    pubsub = _make_pubsub(
        _subscribe_message(),
        _pipeline_message("ROUTED"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)

    pubsub.unsubscribe.assert_called_once()
    pubsub.close.assert_called_once()


# ── SSE frame format ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_content_type_is_event_stream(client, mock_db, mock_redis):
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "ROUTED"}
    mock_redis.pubsub = MagicMock(return_value=_make_pubsub())

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_sse_frame_contains_document_id(client, mock_db, mock_redis):
    _set_oa_auth(client)
    mock_db.fetchrow.return_value = {"pipeline_status": "ROUTED"}
    mock_redis.pubsub = MagicMock(return_value=_make_pubsub())

    resp = await client.get("/v1/ingest/status/doc-001", headers=AUTH_HEADER)
    assert "doc-001" in resp.text


# ── Architecture contract ─────────────────────────────────────────────────────

def test_sse_endpoint_never_polls_db_in_stream_loop():
    """The stream generator must not call db.fetch inside its loop — Redis only."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "routers" / "ingest.py").read_text()
    # Find the _generate() function body
    gen_start = src.index("async def _generate")
    gen_body = src[gen_start:gen_start + 2000]
    # DB calls (fetchrow/fetch/execute) must not appear inside the generator
    assert "await db." not in gen_body, \
        "SSE generator must not make DB calls — use Redis Pub/Sub only"


def test_sse_subscribes_to_correct_redis_channel_pattern():
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "routers" / "ingest.py").read_text()
    assert 'f"sse:doc:{document_id}"' in src or "sse:doc:" in src, \
        "SSE must subscribe to sse:doc:{document_id} channel"


def test_sse_fanout_consumer_publishes_to_pipeline_events_topic():
    import pathlib
    src = (pathlib.Path(__file__).parent.parent.parent /
           "prana-api" / "kafka" / "consumers" / "sse_fanout_consumer.py")
    if not src.exists():
        src = pathlib.Path(__file__).parent.parent / "kafka" / "consumers" / "sse_fanout_consumer.py"
    text = src.read_text()
    assert "prana.pipeline.events" in text, \
        "SSEFanoutConsumer must consume from prana.pipeline.events"
    assert "sse:doc:" in text, \
        "SSEFanoutConsumer must publish to sse:doc:{document_id} Redis channel"
