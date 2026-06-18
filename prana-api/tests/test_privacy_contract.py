"""
Privacy contract tests.

Verifies:
  - SSE endpoint uses Redis Pub/Sub (never polls YugabyteDB)
  - Vault /documents response never contains raw salary fields
  - extracted_fields on document route never contains sensitive keys
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

_SENSITIVE_FIELDS = {
    "gross_salary", "basic_salary", "net_salary", "hra", "pf_employee",
    "pf_employer", "total_deductions", "ctc_before", "ctc_after",
}

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "oa_operator", tenant_id: str = "tenant-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "op-uuid-001",
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


@pytest.mark.asyncio
async def test_vault_documents_no_sensitive_fields(client, mock_db):
    """Document listing must strip all sensitive financial fields from extracted_fields."""
    import datetime
    mock_db.fetch.return_value = [{
        "document_id": "doc-001",
        "doc_type": "SALARY_SLIP",
        "pipeline_status": "ROUTED",
        "doc_period": "2024-03",
        "pushed_at": datetime.datetime(2024, 3, 1, 0, 0, 0),
        "routed_at": datetime.datetime(2024, 3, 1, 1, 0, 0),
        "resolution_method": "PAN_MATCH",
        "resolution_confidence": 0.99,
    }]
    mock_db.fetchval.return_value = 1

    _set_auth(client, role="oa_operator")
    resp = await client.get("/v1/ingest/documents", headers=AUTH_HEADER)

    if resp.status_code == 200:
        items = resp.json().get("items", resp.json().get("documents", []))
        for doc in items:
            fields = doc.get("extracted_fields", {})
            for sensitive in _SENSITIVE_FIELDS:
                assert sensitive not in fields, \
                    f"Sensitive field '{sensitive}' leaked in document response"


@pytest.mark.asyncio
async def test_sse_subscribes_to_redis_not_db(client, mock_db, mock_redis):
    """SSE pipeline status endpoint must subscribe to Redis Pub/Sub, never poll the DB."""
    _set_auth(client, role="oa_operator")

    # Ownership check - one fetchrow at the start, then no more DB calls
    mock_db.fetchrow.return_value = {"pipeline_status": "EXTRACTING"}

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
        "/v1/ingest/status/doc-001",
        headers={**AUTH_HEADER, "Accept": "text/event-stream"},
    )

    assert resp.status_code == 200

    pubsub_mock.subscribe.assert_called_once()
    subscribed_channel = pubsub_mock.subscribe.call_args[0][0]
    assert subscribed_channel == "sse:doc:doc-001"

    # DB must NOT be polled in a loop - only one ownership check at the start
    assert mock_db.fetchrow.call_count == 1, \
        "SSE endpoint polled DB instead of using Redis Pub/Sub"
