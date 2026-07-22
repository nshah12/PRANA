"""
Tests for the Go-Live Checklist upload gate — routers/ingest.py's 3 upload
entrypoints (upload_documents, batch_upload, hrms_upload) each call
_assert_checklist_complete() once per request, before any file processing,
per the approved plan's Part 2 enforcement design.
"""
import hashlib
import hmac
import io
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "oa_operator", tenant_id: str = "tenant-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "op-uuid-001", "user_type": "oa_user", "role": role,
        "tenant_id": tenant_id, "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _incomplete_row():
    return {
        "item_id": "item-1", "tenant_id": None, "item_key": "GRIEVANCE_OFFICER_CONFIGURED",
        "title": "Grievance Officer configured", "description": None, "display_order": 10,
        "is_required": True, "completed_at": None, "completed_by": None, "notes": None,
    }


def _complete_row():
    return {
        "item_id": "item-1", "tenant_id": None, "item_key": "GRIEVANCE_OFFICER_CONFIGURED",
        "title": "Grievance Officer configured", "description": None, "display_order": 10,
        "is_required": True, "completed_at": datetime.now(tz=timezone.utc),
        "completed_by": "oa-admin-1", "notes": None,
    }


# ── /v1/ingest/upload ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_blocked_when_checklist_incomplete(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_incomplete_row()])

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files={"files": ("a.pdf", b"%PDF-1.4 fake" * 10, "application/pdf")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "SETUP_CHECKLIST_INCOMPLETE"
    assert "GRIEVANCE_OFFICER_CONFIGURED" in body["detail"]["missing_item_keys"]


@pytest.mark.asyncio
async def test_upload_succeeds_when_checklist_complete(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_complete_row()])
    # dedup short-circuit (existing file_hash match) — same pattern used by the
    # established happy-path tests in test_ingest_kafka_contract.py, so this
    # test only has to prove the checklist gate itself, not the full S3 write path
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-existing")
    mock_db.execute = AsyncMock()

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files={"files": ("a.pdf", b"%PDF-1.4 fake" * 10, "application/pdf")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_upload_succeeds_when_no_checklist_items_configured(client, mock_db, mock_kafka):
    """Default mock_db.fetch() → [] — no items at all means nothing blocks."""
    _set_auth(client)
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-existing")
    mock_db.execute = AsyncMock()

    resp = await client.post(
        "/v1/ingest/upload",
        headers=AUTH_HEADER,
        files={"files": ("a.pdf", b"%PDF-1.4 fake" * 10, "application/pdf")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202


# ── /v1/ingest/batch ──────────────────────────────────────────────────────────

def _zip_with_pdfs(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, b"%PDF-1.4 fake content" * 10)
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_batch_upload_blocked_when_checklist_incomplete(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_incomplete_row()])

    resp = await client.post(
        "/v1/ingest/batch",
        headers=AUTH_HEADER,
        files={"archive": ("batch.zip", _zip_with_pdfs(["a.pdf"]), "application/zip")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "SETUP_CHECKLIST_INCOMPLETE"


@pytest.mark.asyncio
async def test_batch_upload_succeeds_when_checklist_complete(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.fetch = AsyncMock(return_value=[_complete_row()])
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-001")
    mock_db.execute = AsyncMock()

    resp = await client.post(
        "/v1/ingest/batch",
        headers=AUTH_HEADER,
        files={"archive": ("batch.zip", _zip_with_pdfs(["a.pdf"]), "application/zip")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202


# ── /v1/ingest/hrms/upload ────────────────────────────────────────────────────

_MINIMAL_PDF_BYTES = b"%PDF-1.4 fake content"
SIGNING_SECRET = b"test-signing-secret-32-bytes-pad"
KEY_ID = "test-hrms-key-plaintext-id"
_HRMS_QUERY = "?doc_type=SALARY_SLIP&filename=slip_apr.pdf"


def _valid_signature(body: bytes) -> str:
    return hmac.new(SIGNING_SECRET, body, hashlib.sha256).hexdigest()


def _set_api_key_row(mock_db, tenant_id="tenant-uuid-001"):
    mock_db.fetchrow = AsyncMock(return_value={
        "api_key_id": "api-key-uuid-001",
        "tenant_id": tenant_id,
        "signing_secret_enc": "encrypted-blob",
        "rate_limit_rpm": 1000,
        "status": "ACTIVE",
        "kek_arn": "arn:aws:kms:ap-south-1:000:key/fake",
    })


@pytest.mark.asyncio
async def test_hrms_upload_blocked_when_checklist_incomplete(client, mock_db, mock_kafka, mock_redis, app):
    _set_api_key_row(mock_db)
    app.state.kms_service.unwrap_dek = MagicMock(return_value=SIGNING_SECRET)
    mock_db.fetch = AsyncMock(return_value=[_incomplete_row()])
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)
    resp = await client.post(
        "/v1/ingest/hrms/upload" + _HRMS_QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "SETUP_CHECKLIST_INCOMPLETE"


@pytest.mark.asyncio
async def test_hrms_upload_succeeds_when_checklist_complete(client, mock_db, mock_kafka, mock_redis, app):
    _set_api_key_row(mock_db)
    app.state.kms_service.unwrap_dek = MagicMock(return_value=SIGNING_SECRET)
    mock_db.fetch = AsyncMock(return_value=[_complete_row()])
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    app.state.s3.put_object_async = AsyncMock()

    signature = _valid_signature(_MINIMAL_PDF_BYTES)
    resp = await client.post(
        "/v1/ingest/hrms/upload" + _HRMS_QUERY,
        content=_MINIMAL_PDF_BYTES,
        headers={"X-PRANA-Key-ID": KEY_ID, "X-PRANA-Signature": signature},
    )

    assert resp.status_code == 202
