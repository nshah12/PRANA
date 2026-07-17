"""Tests for POST /v1/ingest/batch — batch (ZIP) upload.

Focused on the document_batch bookkeeping row this handler must create:
BatchProgressWorkflow's write_batch_summary activity UPDATEs a document_batch
row keyed by batch_id — that row has to exist before the workflow starts, and
nothing else in the codebase ever created it (migration 043).
"""
import io
import zipfile
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


def _zip_with_pdfs(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, b"%PDF-1.4 fake content" * 10)
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_batch_upload_inserts_document_batch_row(client, mock_db, mock_kafka):
    _set_auth(client)
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock(return_value="doc-uuid-001")

    resp = await client.post(
        "/v1/ingest/batch",
        headers=AUTH_HEADER,
        files={"archive": ("batch.zip", _zip_with_pdfs(["a.pdf", "b.pdf"]), "application/zip")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202
    insert_call = next(
        c for c in mock_db.execute.call_args_list if "INSERT INTO document_batch" in c.args[0]
    )
    sql, *args = insert_call.args
    assert "PROCESSING" in sql or "PROCESSING" in args
    assert "tenant-uuid-001" in args
    assert 2 in args  # total_files


@pytest.mark.asyncio
async def test_batch_upload_skips_document_batch_row_when_all_files_rejected(client, mock_db, mock_kafka):
    """No accepted files (e.g. all wrong extension) — nothing for BatchProgressWorkflow
    to track, so the bookkeeping row must not be created."""
    _set_auth(client)
    mock_db.execute = AsyncMock()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("not_a_pdf.exe", b"binary")
    buf.seek(0)

    resp = await client.post(
        "/v1/ingest/batch",
        headers=AUTH_HEADER,
        files={"archive": ("batch.zip", buf.read(), "application/zip")},
        data={"doc_type": "SALARY_SLIP"},
    )

    assert resp.status_code == 202
    assert not any("INSERT INTO document_batch" in c.args[0] for c in mock_db.execute.call_args_list)
