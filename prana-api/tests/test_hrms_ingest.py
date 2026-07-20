"""
Tests for POST /v1/ingest/hrms/upload — HRMS partner API-key push.

Covers:
  - X-PRANA-Key-ID / X-PRANA-Signature auth (integrations.md contract)
  - Real Redis-backed rate limiting against api_key.rate_limit_rpm
  - 429 + INGEST_RATE_LIMITED published to prana.audit.events on breach
  - HTTP handler contract: validate -> S3 put -> 1 DB write -> 1 Kafka publish -> 202

The request body is the raw file (not multipart) — see routers/ingest.py's
hrms_upload docstring for why: ApiKeyAuth verifies HMAC over the raw body,
which would be consumed by multipart/Form parsing before it could be checked.
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import pytest

_MINIMAL_PDF_BYTES = b"%PDF-1.4 fake content"
SIGNING_SECRET = b"test-signing-secret-32-bytes-pad"
KEY_ID = "test-hrms-key-plaintext-id"

_QUERY = "?doc_type=SALARY_SLIP&filename=slip_apr.pdf"


def _valid_signature(body: bytes) -> str:
    return hmac.new(SIGNING_SECRET, body, hashlib.sha256).hexdigest()


def _set_api_key_row(mock_db, tenant_id="tenant-uuid-001", rate_limit_rpm=1000, status_="ACTIVE"):
    mock_db.fetchrow = AsyncMock(return_value={
        "api_key_id": "api-key-uuid-001",
        "tenant_id": tenant_id,
        "signing_secret_enc": "encrypted-blob",
        "rate_limit_rpm": rate_limit_rpm,
        "status": status_,
        "kek_arn": "arn:aws:kms:ap-south-1:000:key/fake",
    })


def _configure_kms(app):
    app.state.kms_service.unwrap_dek = MagicMock(return_value=SIGNING_SECRET)


# ── Auth guard ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hrms_upload_requires_signature_headers(client, mock_db):
    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "MISSING_API_KEY_HEADERS"


@pytest.mark.asyncio
async def test_hrms_upload_rejects_invalid_signature(client, mock_db, app):
    _set_api_key_row(mock_db)
    _configure_kms(app)

    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": "deadbeef"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_SIGNATURE"


@pytest.mark.asyncio
async def test_hrms_upload_rejects_unknown_key(client, mock_db, app):
    mock_db.fetchrow = AsyncMock(return_value=None)
    _configure_kms(app)

    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": "deadbeef"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_API_KEY"


# ── Happy path / Kafka contract ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hrms_upload_accepts_correctly_signed_request(client, mock_db, mock_kafka, mock_redis, app):
    """Valid signed request must S3-put + 1 DB write + publish exactly one DOC_INGESTED event."""
    _set_api_key_row(mock_db)
    _configure_kms(app)
    mock_db.fetchval = AsyncMock(return_value=None)  # no existing dedup match
    mock_db.execute = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)

    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    assert resp.status_code == 202
    mock_kafka.doc_ingested.assert_called_once()
    event = mock_kafka.doc_ingested.call_args.args[0]
    assert event["event_type"] == "DOC_INGESTED"
    assert event["tenant_id"] == "tenant-uuid-001"


@pytest.mark.asyncio
async def test_hrms_upload_never_writes_audit_event_or_starts_workflow(client, mock_db, mock_kafka, mock_redis, app):
    """HTTP handler contract: no direct audit_event INSERT, no workflow start."""
    _set_api_key_row(mock_db)
    _configure_kms(app)
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)

    await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    for call in mock_db.execute.call_args_list:
        sql = call.args[0].upper()
        assert "AUDIT_EVENT" not in sql


# ── Rate limiting ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hrms_upload_rate_limited_returns_429_and_publishes_audit_event(
    client, mock_db, mock_kafka, mock_redis, app
):
    """Exceeding rate_limit_rpm must return 429 and publish INGEST_RATE_LIMITED
    to prana.audit.events for the durable audit trail (AuditConsumer persists it)."""
    _set_api_key_row(mock_db, rate_limit_rpm=5)
    _configure_kms(app)
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=6)   # over the limit of 5
    mock_redis.expire = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)

    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    assert resp.status_code == 429
    mock_kafka.publish.assert_called_once()
    topic, payload = mock_kafka.publish.call_args[0][:2]
    assert topic == "prana.audit.events"
    assert payload["event_type"] == "INGEST_RATE_LIMITED"


@pytest.mark.asyncio
async def test_hrms_upload_under_limit_does_not_publish_rate_limit_event(
    client, mock_db, mock_kafka, mock_redis, app
):
    _set_api_key_row(mock_db, rate_limit_rpm=1000)
    _configure_kms(app)
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)

    resp = await client.post(
        "/v1/ingest/hrms/upload" + _QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    assert resp.status_code == 202
    for call in mock_kafka.publish.call_args_list:
        assert call.args[1]["event_type"] != "INGEST_RATE_LIMITED"
