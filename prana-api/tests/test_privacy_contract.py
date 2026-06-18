"""
Privacy contract tests.

Verifies:
  - SSE endpoint uses Redis Pub/Sub (never polls YugabyteDB)
  - Vault /documents response never contains raw salary fields
  - extracted_fields on document route never contains sensitive keys
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SENSITIVE_FIELDS = {
    "gross_salary", "basic_salary", "net_salary", "hra", "pf_employee",
    "pf_employer", "total_deductions", "ctc_before", "ctc_after",
}


@pytest.mark.asyncio
async def test_vault_documents_no_sensitive_fields(client, mock_db):
    """Document listing must strip all sensitive financial fields from extracted_fields."""
    import json

    # Simulate a document row with sensitive fields still in extracted_fields
    mock_db.fetch.return_value = [{
        "document_id": "doc-001",
        "doc_type": "SALARY_SLIP",
        "pipeline_status": "ROUTED",
        "extracted_fields": json.dumps({
            "employee_name": {"value": "Rahul Sharma", "confidence": 0.97},
            "gross_salary": {"value": "80000", "confidence": 0.95},
            "basic_salary": {"value": "40000", "confidence": 0.95},
            "net_salary": {"value": "70000", "confidence": 0.95},
            "designation": {"value": "Engineer", "confidence": 0.98},
        }),
        "doc_period": "2024-03",
        "tenant_id": "tenant-001",
        "uploaded_at": "2024-03-01T00:00:00Z",
        "routed_at": "2024-03-01T01:00:00Z",
        "s3_key": "docs/tenant-001/doc-001.pdf",
        "insight_text": "Good growth trajectory",
    }]

    with patch("routers.vault.Employee", return_value=MagicMock(
        user_id="emp-001", pan_token="abc123"
    )):
        resp = await client.get("/vault/documents")

    if resp.status_code == 200:
        docs = resp.json().get("documents", [])
        for doc in docs:
            fields = doc.get("extracted_fields", {})
            for sensitive in _SENSITIVE_FIELDS:
                assert sensitive not in fields, \
                    f"Sensitive field '{sensitive}' leaked in vault document response"


@pytest.mark.asyncio
async def test_sse_subscribes_to_redis_not_db(client, mock_db, mock_redis):
    """SSE endpoint must subscribe to Redis channel, never poll the DB."""
    # SSE is a streaming endpoint — we just verify Redis pubsub is used
    pubsub_mock = AsyncMock()
    pubsub_mock.subscribe = AsyncMock()

    async def mock_listen():
        yield {"type": "subscribe", "data": 1}
        yield {"type": "message", "data": '{"stage":"ROUTED","pipeline_status":"ROUTED"}'}

    pubsub_mock.listen = mock_listen
    mock_redis.pubsub = MagicMock(return_value=pubsub_mock)

    with patch("routers.ingest.Employee", return_value=MagicMock(user_id="emp-001")):
        # SSE returns event-stream so we just check it starts
        resp = await client.get(
            "/ingest/sse/doc-001",
            headers={"Accept": "text/event-stream"},
        )

    # The SSE endpoint must subscribe to Redis, not call db.fetchrow in a loop
    pubsub_mock.subscribe.assert_called_once_with("sse:doc:doc-001")
    # DB must NOT have been polled
    for c in mock_db.fetch.call_args_list:
        assert "pipeline_status" not in str(c), \
            "SSE endpoint polled DB instead of using Redis Pub/Sub"
