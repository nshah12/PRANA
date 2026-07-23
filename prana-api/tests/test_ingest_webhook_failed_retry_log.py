"""
Tests for POST /v1/ingest/upload's HRMS_WEBHOOK_FAILED publish on file rejection.

Regression: the published event carried filename/actor_id/reason but no
request_id, while kafka/consumers/integration_consumer.py's
_handle_hrms_failure looks up retry state by request_id against a table
(api_ingest_log) that didn't exist anywhere in schema.sql — every real
rejection would hit an undefined-table error (silently swallowed by the
consumer's broad except) and retry_count was never actually tracked.
"""
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


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


@pytest.mark.asyncio
async def test_rejected_upload_logs_api_ingest_row_and_publishes_request_id(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files={"files": ("evil.pdf", io.BytesIO(b"MZ\x90\x00 not a pdf"), "application/pdf")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202

    insert_calls = [c for c in mock_db.execute.call_args_list if "INSERT INTO api_ingest_log" in c.args[0]]
    assert insert_calls, "must INSERT a row into api_ingest_log on rejection"
    _, request_id, *_rest = insert_calls[0].args

    mock_kafka.integration_event.assert_awaited()
    event = mock_kafka.integration_event.await_args.args[0]
    assert event["event_type"] == "HRMS_WEBHOOK_FAILED"
    assert event["request_id"] == request_id
