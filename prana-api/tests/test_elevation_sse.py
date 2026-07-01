"""
Tests for elevation SSE stream — GET /v1/org/elevations/{elevation_id}/status

Architecture under test:
  OA-Operator/Admin → GET /org/elevations/{id}/status
    → verify tenant ownership (DB)
    → yield current elevation status immediately
    → subscribe to Redis Pub/Sub sse:elevation:{id}
    → yield each status-change event until terminal state or 10-min timeout
    → approve/deny/end-early publish to Redis channel via _publish_elevation_sse()

Contracts:
  1. Auth guard: requires oa_operator or oa_admin
  2. Tenant isolation: elevation must belong to caller's tenant
  3. Terminal states (ACTIVE/DENIED/ENDED_EARLY/ENDED) return immediately, no subscription
  4. In-progress (PENDING) subscribes to sse:elevation:{id}
  5. SSE frame format: data: <json>\n\n with elevation_id and status fields
  6. Unsubscribes + closes on completion (no resource leak)
  7. approve/deny/end-early publish to Redis after DB update
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role="oa_operator", tenant_id="tenant-001", user_id="oa-uuid-001"):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _make_pubsub(*messages):
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()

    async def _listen():
        for msg in messages:
            yield msg

    pubsub.listen = _listen
    return pubsub


def _elev_message(new_status: str, elevation_id: str = "elev-001", expires_at=None) -> dict:
    return {
        "type": "message",
        "data": json.dumps({"elevation_id": elevation_id, "status": new_status, "expires_at": expires_at}),
    }


def _sub_message() -> dict:
    return {"type": "subscribe", "data": 1}


# ── Auth boundary ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevation_sse_requires_auth(client):
    resp = await client.get("/v1/org/elevations/elev-001/status")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_elevation_sse_employee_blocked(client):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "emp-001", "user_type": "employee", "role": "employee",
        "tenant_id": "tenant-001", "jti": "s1",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    assert resp.status_code in (401, 403)


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevation_sse_returns_404_for_wrong_tenant(client, mock_db, mock_redis):
    _set_auth(client, tenant_id="tenant-002")
    mock_db.fetchrow.return_value = None
    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "ELEVATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_elevation_sse_tenant_id_in_db_query(client, mock_db, mock_redis):
    _set_auth(client, tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"status": "ACTIVE"}
    mock_redis.pubsub = MagicMock(return_value=_make_pubsub())

    await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    query = mock_db.fetchrow.call_args[0][0]
    assert "tenant_id" in query


# ── Terminal states — immediate return, no subscription ──────────────────────

@pytest.mark.asyncio
async def test_elevation_sse_already_active_returns_immediately(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "ACTIVE"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "ACTIVE" in resp.text
    pubsub.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_elevation_sse_already_denied_returns_immediately(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "DENIED"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "DENIED" in resp.text
    pubsub.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_elevation_sse_already_ended_early_returns_immediately(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "ENDED_EARLY"}
    pubsub = _make_pubsub()
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    assert "ENDED_EARLY" in resp.text
    pubsub.subscribe.assert_not_called()


# ── PENDING — subscribes and waits ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevation_sse_pending_subscribes_to_correct_channel(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "PENDING"}
    pubsub = _make_pubsub(
        _sub_message(),
        _elev_message("ACTIVE"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    assert resp.status_code == 200
    pubsub.subscribe.assert_called_once_with("sse:elevation:elev-001")


@pytest.mark.asyncio
async def test_elevation_sse_emits_initial_then_decision(client, mock_db, mock_redis):
    """First frame = PENDING from DB. Second frame = ACTIVE from Redis."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "PENDING"}
    pubsub = _make_pubsub(
        _sub_message(),
        _elev_message("ACTIVE"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    body = resp.text
    assert "PENDING" in body
    assert "ACTIVE" in body


@pytest.mark.asyncio
async def test_elevation_sse_stops_after_active(client, mock_db, mock_redis):
    """Stream must close after ACTIVE — must not emit events that follow."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "PENDING"}
    pubsub = _make_pubsub(
        _sub_message(),
        _elev_message("ACTIVE"),
        _elev_message("DENIED"),   # must NOT appear — stream already closed
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    body = resp.text

    active_idx = body.index("ACTIVE")
    assert "DENIED" not in body[active_idx:], "Stream must not emit after ACTIVE terminal"


@pytest.mark.asyncio
async def test_elevation_sse_stops_after_denied(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "PENDING"}
    pubsub = _make_pubsub(
        _sub_message(),
        _elev_message("DENIED"),
        _elev_message("ACTIVE"),   # must NOT appear
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    denied_idx = resp.text.index("DENIED")
    assert "ACTIVE" not in resp.text[denied_idx:]


@pytest.mark.asyncio
async def test_elevation_sse_unsubscribes_on_completion(client, mock_db, mock_redis):
    """pubsub.unsubscribe and pubsub.close must be called — no resource leak."""
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "PENDING"}
    pubsub = _make_pubsub(
        _sub_message(),
        _elev_message("ACTIVE"),
    )
    mock_redis.pubsub = MagicMock(return_value=pubsub)

    await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)

    pubsub.unsubscribe.assert_called_once()
    pubsub.close.assert_called_once()


# ── SSE frame format ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevation_sse_content_type(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "ACTIVE"}
    mock_redis.pubsub = MagicMock(return_value=_make_pubsub())

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_elevation_sse_frame_contains_elevation_id(client, mock_db, mock_redis):
    _set_auth(client)
    mock_db.fetchrow.return_value = {"status": "ACTIVE"}
    mock_redis.pubsub = MagicMock(return_value=_make_pubsub())

    resp = await client.get("/v1/org/elevations/elev-001/status", headers=AUTH_HEADER)
    assert "elev-001" in resp.text


# ── Publisher side: approve/deny/end-early publish to Redis ──────────────────

@pytest.mark.asyncio
async def test_approve_publishes_active_to_redis_sse_channel(client, mock_db, mock_redis):
    """Approving an elevation must fire a Redis publish to sse:elevation:{id}."""
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")
    mock_db.fetchrow.return_value = {
        "requestor_id": "op-uuid-001",
        "duration_hours": 4,
        "status": "PENDING",
    }
    mock_db.execute = AsyncMock()
    mock_redis.publish = AsyncMock()

    resp = await client.post("/v1/org/elevations/elev-001/approve", headers=AUTH_HEADER)

    assert resp.status_code == 200
    # Redis publish must have been scheduled (create_task) — may need a brief yield
    await __import__("asyncio").sleep(0)
    mock_redis.publish.assert_called_once()
    channel = mock_redis.publish.call_args[0][0]
    assert channel == "sse:elevation:elev-001"
    payload = json.loads(mock_redis.publish.call_args[0][1])
    assert payload["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_deny_publishes_denied_to_redis_sse_channel(client, mock_db, mock_redis):
    _set_auth(client, role="oa_admin", user_id="admin-uuid-001")
    mock_db.execute = AsyncMock()
    mock_redis.publish = AsyncMock()

    resp = await client.post("/v1/org/elevations/elev-001/deny", headers=AUTH_HEADER)

    assert resp.status_code == 200
    await __import__("asyncio").sleep(0)
    mock_redis.publish.assert_called_once()
    channel = mock_redis.publish.call_args[0][0]
    assert channel == "sse:elevation:elev-001"
    payload = json.loads(mock_redis.publish.call_args[0][1])
    assert payload["status"] == "DENIED"


@pytest.mark.asyncio
async def test_end_early_publishes_ended_early_to_redis_sse_channel(client, mock_db, mock_redis):
    _set_auth(client, role="oa_operator", user_id="op-uuid-001")
    mock_db.execute = AsyncMock()
    mock_redis.publish = AsyncMock()

    resp = await client.post("/v1/org/elevations/elev-001/end-early", headers=AUTH_HEADER)

    assert resp.status_code == 200
    await __import__("asyncio").sleep(0)
    mock_redis.publish.assert_called_once()
    payload = json.loads(mock_redis.publish.call_args[0][1])
    assert payload["status"] == "ENDED_EARLY"


# ── Architecture contract ─────────────────────────────────────────────────────

def test_elevation_sse_never_polls_db_in_stream_loop():
    """The stream generator must not call db.fetch inside its loop — Redis only."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "routers" / "oa_users.py").read_text()
    gen_start = src.index("async def _generate")
    gen_body = src[gen_start:gen_start + 2000]
    assert "await db." not in gen_body, "SSE generator must not make DB calls"


def test_elevation_sse_channel_uses_sse_elevation_prefix():
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "routers" / "oa_users.py").read_text()
    assert "sse:elevation:" in src, "Elevation SSE must use sse:elevation:{id} channel"
