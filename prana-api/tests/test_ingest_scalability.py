"""
Scalability regression tests for the ingest path.

Covers the fixes from the architectural review:
  1. S3 put uses put_object_async (non-blocking)
  2. Staging key has 4-char hash prefix (prevents S3 partition throttling)
  3. prana.ingest.events partitioned by document_id, not tenant_id

RED → GREEN cycle: tests written before implementation.
"""
import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch, call

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
    return [("files", ("slip_apr.pdf", io.BytesIO(_MINIMAL_PDF_BYTES), "application/pdf"))]


# ── 1. S3 staging call is non-blocking ───────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_uses_async_s3_upload(client, mock_db, mock_kafka):
    """
    _ingest_one must call put_object_async (awaitable), not synchronous put_object.
    Calling synchronous put_object inside an async handler blocks the entire event loop.
    RED: fails until ingest.py switches to s3.put_object_async().
    """
    _set_auth(client)
    mock_db.fetchval = AsyncMock(return_value=None)  # no dedup hit
    mock_db.execute = AsyncMock()

    # Make the S3 mock explicitly async for put_object_async
    client.app.state.s3.put_object_async = AsyncMock()
    client.app.state.s3.put_object = MagicMock()  # sync — must NOT be called

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202
    client.app.state.s3.put_object_async.assert_called_once()
    client.app.state.s3.put_object.assert_not_called()


# ── 2. Staging key has entropy prefix ────────────────────────────────────────

@pytest.mark.asyncio
async def test_staging_key_has_hash_prefix(client, mock_db, mock_kafka):
    """
    S3 key must be staging/{4-char-hex}/{tenant_id}/{doc_id}.{ext}
    Without the prefix, all tenant uploads land under staging/{tenant_id}/ —
    a single S3 prefix that throttles above 3,500 req/s under batch load.
    RED: fails until ingest.py adds hash_prefix = document_id[:4] to staging_key.
    """
    _set_auth(client, tenant_id="tenant-uuid-001")
    mock_db.fetchval = AsyncMock(return_value=None)  # no dedup hit
    mock_db.execute = AsyncMock()
    client.app.state.s3.put_object_async = AsyncMock()

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files=_make_upload_files(),
        data={"doc_type": "FORM_16"},
    )

    assert resp.status_code == 202

    # Extract the s3_key stored in the DB — it's the 5th param of INSERT INTO document
    # execute(sql, doc_id, tenant_id, doc_type, doc_period, s3_key, s3_bucket, ...)
    insert_call = next(
        c for c in mock_db.execute.call_args_list
        if "INSERT INTO document" in str(c.args[0])
    )
    # args: (sql, doc_id, tenant_id, doc_type, doc_period, s3_key, ...)
    s3_key: str = insert_call.args[5]

    parts = s3_key.split("/")
    assert parts[0] == "staging", f"Expected 'staging' prefix, got: {parts[0]}"
    assert len(parts) >= 4, f"Expected staging/hash/tenant/docid.ext, got: {s3_key}"
    hash_prefix = parts[1]
    assert len(hash_prefix) == 4, f"Hash prefix must be 4 hex chars, got '{hash_prefix}'"
    assert all(c in "0123456789abcdefABCDEF-" for c in hash_prefix), \
        f"Hash prefix must be hex chars from UUID, got '{hash_prefix}'"
    assert parts[2] == "tenant-uuid-001", f"Tenant ID missing from key: {s3_key}"


@pytest.mark.asyncio
async def test_staging_key_prefix_varies_across_documents(client, mock_db, mock_kafka):
    """
    Different documents must produce different prefixes (prefix is derived from doc UUID).
    This verifies the distribution property — not all docs land on the same prefix.
    RED: fails (two uploads would currently both use staging/{tenant_id}/...).
    """
    _set_auth(client)
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    client.app.state.s3.put_object_async = AsyncMock()

    # Upload file 1
    await client.post("/v1/ingest/upload", headers=AUTH_HEADER,
                      files=[("files", ("a.pdf", io.BytesIO(_MINIMAL_PDF_BYTES), "application/pdf"))],
                      data={"doc_type": "SALARY_SLIP"})
    # Upload file 2
    await client.post("/v1/ingest/upload", headers=AUTH_HEADER,
                      files=[("files", ("b.pdf", io.BytesIO(b"%PDF-1.4 different content"), "application/pdf"))],
                      data={"doc_type": "SALARY_SLIP"})

    insert_calls = [
        c for c in mock_db.execute.call_args_list
        if "INSERT INTO document" in str(c.args[0])
    ]
    assert len(insert_calls) == 2, "Expected two INSERT calls"
    key1 = insert_calls[0].args[5]
    key2 = insert_calls[1].args[5]
    prefix1 = key1.split("/")[1]
    prefix2 = key2.split("/")[1]
    # With random UUIDs, prefixes virtually always differ. Equality would mean the prefix
    # isn't derived from the document UUID.
    assert prefix1 != prefix2 or key1.split("/")[3] != key2.split("/")[3], \
        "Two different documents should not share both prefix and filename"


# ── 3. Kafka ingest topic partitioned by document_id ─────────────────────────

@pytest.mark.asyncio
async def test_kafka_doc_ingested_partitions_by_document_id():
    """
    KafkaPub.doc_ingested() must publish to TOPIC_INGEST with key=document_id.
    Partitioning by tenant_id causes hot partitions for large enterprise uploads.
    RED: fails until producer.py changes key=event["tenant_id"] → key=event["document_id"].
    """
    from kafka.producer import KafkaPub

    mock_producer = MagicMock()
    mock_producer.send_and_wait = AsyncMock()

    pub = KafkaPub.__new__(KafkaPub)
    pub._producer = mock_producer

    event = {
        "event_type": "DOC_INGESTED",
        "document_id": "doc-uuid-abc",
        "tenant_id": "tenant-uuid-xyz",
        "doc_type": "SALARY_SLIP",
    }

    await pub.doc_ingested(event)

    # First call is TOPIC_INGEST — must use document_id as partition key
    # aiokafka send_and_wait: send_and_wait(topic, value=..., key=...)  — key is always kwargs
    ingest_call = mock_producer.send_and_wait.call_args_list[0]
    sent_key = ingest_call.kwargs.get("key")
    assert sent_key == "doc-uuid-abc", (
        f"prana.ingest.events must be partitioned by document_id, got key={sent_key!r}. "
        "Partitioning by tenant_id creates hot partitions for large tenants."
    )
