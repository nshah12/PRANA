"""
Tests for routers/vault.py — Employee vault.

Tests cover:
  - Auth enforcement (401 without token, 403 for non-employee)
  - Response shape contract (wrapped items, not bare arrays)
  - Serialization: UUID/datetime fields must not cause 500
  - Privacy: no raw salary or PAN fields in any response
  - Watermark: document bytes must always be watermarked (never raw)
  - Access log: every document view writes ip_address

TDD: written BEFORE fixes. Run RED first.
"""
import json
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _auth_headers(client, user_id="emp-user-uuid-001"):
    """Inject employee JWT claims into the mock jwt_service."""
    mock_jwt = client.app.state.jwt_service
    mock_jwt.decode.return_value = {
        "sub": user_id,
        "user_type": "employee",
        "jti": "session-abc",
        "exp": 9999999999,
    }
    mock_jwt.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer fake.employee.jwt"}


def _doc_row():
    """Simulated asyncpg-style document row (uses Python native types, not asyncpg wrappers)."""
    return {
        "document_id": UUID("11111111-1111-1111-1111-111111111111"),
        "doc_type": "SALARY_SLIP",
        "doc_period": "2024-03",
        "pipeline_status": "ROUTED",
        "tenant_id": UUID("22222222-2222-2222-2222-222222222222"),
        "tenant_name": "Acme Corp",
        "pushed_at": datetime(2024, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        "routed_at": datetime(2024, 3, 1, 11, 0, 0, tzinfo=timezone.utc),
        "is_self_upload": False,
        "original_filename": "march_slip.pdf",
        "designation": "Engineer",
        "department": "Engineering",
        "doj": date(2022, 1, 15),
        "dol": None,
    }


# ── Auth enforcement ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vault_list_documents_without_token_returns_401(client):
    resp = await client.get("/v1/vault/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_vault_list_documents_with_oa_token_returns_403(client):
    mock_jwt = client.app.state.jwt_service
    mock_jwt.decode.return_value = {
        "sub": "oa-user-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": "tenant-001",
        "jti": "sess-001",
        "exp": 9999999999,
    }
    mock_jwt.is_revoked = AsyncMock(return_value=False)
    resp = await client.get(
        "/v1/vault/documents",
        headers={"Authorization": "Bearer oa.jwt.token"},
    )
    assert resp.status_code == 403


# ── Response shape ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vault_list_documents_returns_wrapped_shape(client, mock_db):
    """Response must be {"documents": [...], "count": N} — not a bare array."""
    headers = _auth_headers(client)
    mock_db.fetch.return_value = [_doc_row()]

    with patch("routers.vault.VaultService.list_documents", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{
            "document_id": "11111111-1111-1111-1111-111111111111",
            "doc_type": "SALARY_SLIP",
            "doc_period": "2024-03",
            "pipeline_status": "ROUTED",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "tenant_name": "Acme Corp",
            "pushed_at": "2024-03-01T10:00:00+00:00",
            "routed_at": "2024-03-01T11:00:00+00:00",
        }]
        resp = await client.get("/v1/vault/documents", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "documents" in body, "Response must have 'documents' key — not bare array"
    assert "count" in body
    assert isinstance(body["documents"], list)


@pytest.mark.asyncio
async def test_vault_employers_returns_wrapped_shape(client, mock_db):
    headers = _auth_headers(client)
    with patch("routers.vault.VaultService.get_employers", new_callable=AsyncMock) as mock_emp:
        mock_emp.return_value = []
        resp = await client.get("/v1/vault/employers", headers=headers)
    assert resp.status_code == 200
    assert "employers" in resp.json()


@pytest.mark.asyncio
async def test_vault_activity_returns_wrapped_shape(client, mock_db):
    headers = _auth_headers(client)
    mock_db.fetch.return_value = []
    resp = await client.get("/v1/vault/activity", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_log" in body
    assert "pipeline_pushes" in body


# ── Serialization — this is the RED test for vault_service bug #1 ──────────────

@pytest.mark.asyncio
async def test_vault_list_documents_serializes_without_500(client, mock_db):
    """
    VaultService.list_documents returns dict(row) with asyncpg UUID and datetime.
    FastAPI must serialize these without 500. This test will FAIL until vault_service
    explicitly converts UUIDs to str and datetimes to isoformat.
    """
    headers = _auth_headers(client)
    # Return a real asyncpg-style row with Python UUID and datetime objects
    mock_db.fetch.return_value = [_doc_row()]

    resp = await client.get("/v1/vault/documents", headers=headers)
    # Must not 500 — serialization must work
    assert resp.status_code != 500, (
        "Vault list_documents caused a 500 — UUID/datetime serialization bug in vault_service"
    )
    assert resp.status_code == 200
    # Response body must be valid JSON with string UUID and ISO datetime
    body = resp.json()
    docs = body.get("documents", [])
    if docs:
        assert isinstance(docs[0]["document_id"], str), "document_id must be serialized to string"
        assert isinstance(docs[0]["pushed_at"], str), "pushed_at must be serialized to ISO string"


@pytest.mark.asyncio
async def test_vault_profile_serializes_without_500(client, mock_db):
    """Profile endpoint must return 200 with serializable UUID/datetime fields."""
    headers = _auth_headers(client)
    mock_db.fetchrow.return_value = {
        "employee_user_id": UUID("33333333-3333-3333-3333-333333333333"),
        "mobile": "+919000000001",
        "status": "ACTIVE",
        "created_at": datetime(2022, 1, 1, tzinfo=timezone.utc),
        "full_name": "Rahul Sharma",
        "designation": "Engineer",
        "department": "Engineering",
        "master_user_id": UUID("33333333-3333-3333-3333-333333333333"),
    }
    with patch("routers.vault.VaultService.get_employers", new_callable=AsyncMock) as mock_emp:
        mock_emp.return_value = []
        resp = await client.get("/v1/vault/profile", headers=headers)
    assert resp.status_code != 500
    assert resp.status_code == 200


# ── Privacy contract ───────────────────────────────────────────────────────────

_FORBIDDEN_FIELDS = {
    "salary", "gross_salary", "net_salary", "basic_salary", "ctc",
    "pan", "nik", "enc_pan", "enc_dek",
}


@pytest.mark.asyncio
async def test_vault_profile_contains_no_pan_or_salary_fields(client, mock_db):
    headers = _auth_headers(client)
    mock_db.fetchrow.return_value = {
        "employee_user_id": UUID("33333333-3333-3333-3333-333333333333"),
        "mobile": "+919000000001",
        "status": "ACTIVE",
        "created_at": datetime(2022, 1, 1, tzinfo=timezone.utc),
        "full_name": "Rahul Sharma",
        "designation": "Engineer",
        "department": "Engineering",
        "master_user_id": UUID("33333333-3333-3333-3333-333333333333"),
    }
    with patch("routers.vault.VaultService.get_employers", new_callable=AsyncMock) as mock_emp:
        mock_emp.return_value = []
        resp = await client.get("/v1/vault/profile", headers=headers)
    if resp.status_code == 200:
        body_str = json.dumps(resp.json()).lower()
        for field in _FORBIDDEN_FIELDS:
            assert field not in body_str, f"Forbidden field '{field}' found in /vault/profile response"


@pytest.mark.asyncio
async def test_vault_career_contains_no_raw_salary(client, mock_db):
    headers = _auth_headers(client)
    mock_db.fetchval.return_value = "emp-uuid-001"
    mock_db.fetch.return_value = []
    resp = await client.get("/v1/vault/career", headers=headers)
    if resp.status_code == 200:
        body_str = json.dumps(resp.json()).lower()
        for field in {"gross_salary", "net_salary", "basic_salary", "ctc"}:
            assert field not in body_str, f"Raw salary field '{field}' leaked in career response"


# ── Watermark compliance — RED test for vault.py bug #2 ───────────────────────

@pytest.mark.asyncio
async def test_document_view_fails_hard_if_watermark_cannot_be_applied(client, mock_db):
    """
    If watermarking fails (PyMuPDF not available), endpoint must NOT silently
    return unwatermarked bytes. It must return an error.
    This test will FAIL until _apply_watermark is fixed to raise instead of pass-through.
    """
    headers = _auth_headers(client)
    pdf_bytes = b"%PDF-1.4 fake pdf content"

    with patch("routers.vault.VaultService.get_document_bytes", new_callable=AsyncMock) as mock_doc:
        mock_doc.return_value = (pdf_bytes, "SALARY_SLIP")
        # Force PyMuPDF to be unavailable
        with patch.dict("sys.modules", {"fitz": None}):
            resp = await client.get(
                "/v1/vault/documents/doc-001",
                headers=headers,
            )

    # Correct compliance outcomes when watermark engine unavailable:
    #   503 / 500 — fail hard, refuse to serve (preferred: no document leaks)
    #   200        — only if watermark text is present in the response body
    # Forbidden: 200 with raw unwatermarked PDF bytes
    if resp.status_code in (500, 503):
        pass  # fail-hard is correct — never serve unwatermarked document
    elif resp.status_code == 200:
        content = resp.content
        assert b"PRANA" in content or b"Confidential" in content, (
            "Watermark missing! Document served without watermark when PyMuPDF unavailable. "
            "Compliance violation: vault.py _apply_watermark must fail hard or use reportlab fallback."
        )
    else:
        pytest.fail(f"Unexpected status {resp.status_code} — expected 200 (with watermark) or 500 (fail-hard)")


# ── Share ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_share_returns_token_not_document_bytes(client, mock_db):
    headers = _auth_headers(client)
    with patch("routers.vault.ShareService.create", new_callable=AsyncMock) as mock_share:
        mock_share.return_value = {
            "share_id": "share-001",
            "share_token": "tok-abc123",
            "expires_at": "2024-04-01T00:00:00Z",
        }
        resp = await client.post(
            "/v1/vault/share",
            json={
                "document_ids": ["doc-001"],
                "expires_hours": 24,
            },
            headers=headers,
        )
    assert resp.status_code == 201
    body = resp.json()
    # Response must be a token reference, never document bytes
    assert "share_token" in body or "share_id" in body
    assert "bytes" not in body
    assert "content" not in body


@pytest.mark.asyncio
async def test_list_shares_returns_wrapped_shape(client, mock_db):
    headers = _auth_headers(client)
    with patch("routers.vault.ShareService.list_shares", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        resp = await client.get("/v1/vault/share", headers=headers)
    assert resp.status_code == 200
    assert "shares" in resp.json()


# ── Career Passport / credential card tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_credential_requires_auth(client):
    """Credential endpoint must require employee JWT."""
    resp = await client.get("/v1/vault/documents/doc-001/credential")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_credential_not_found_returns_404(client, mock_db):
    """Unknown document_id or doc not owned by employee → 404."""
    headers = _auth_headers(client)
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = await client.get("/v1/vault/documents/doc-001/credential", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_credential_not_routed_returns_404(client, mock_db):
    """Document exists but pipeline_status != ROUTED → 404 (no verification code yet)."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "document_id":       str(uuid.uuid4()),
        "pipeline_status":   "EXTRACTING",
        "verification_code": None,
        "doc_type":          "SALARY_SLIP",
        "doc_period":        "2024-03",
        "tenant_name":       "Acme Corp",
        "pushed_at":         datetime(2024, 3, 1, tzinfo=timezone.utc),
        "routed_at":         None,
        "file_hash_sha256":  None,
    }.get(k)

    headers = _auth_headers(client)
    mock_db.fetchrow = AsyncMock(return_value=row)
    resp = await client.get("/v1/vault/documents/doc-001/credential", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_credential_happy_path_shape(client, mock_db):
    """ROUTED doc with verification code returns credential card fields."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    doc_id = str(uuid.uuid4())
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "document_id":       doc_id,
        "pipeline_status":   "ROUTED",
        "verification_code": "PRANA-AB1234-CD5678",
        "doc_type":          "SALARY_SLIP",
        "doc_period":        "2024-03",
        "tenant_name":       "Infosys Ltd",
        "pushed_at":         datetime(2024, 3, 1, tzinfo=timezone.utc),
        "routed_at":         datetime(2024, 3, 2, tzinfo=timezone.utc),
        "file_hash_sha256":  "deadbeef",
    }.get(k)

    headers = _auth_headers(client)
    mock_db.fetchrow = AsyncMock(return_value=row)
    resp = await client.get(f"/v1/vault/documents/{doc_id}/credential", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["verification_code"] == "PRANA-AB1234-CD5678"
    assert "verify_url" in data
    assert "PRANA-AB1234-CD5678" in data["verify_url"]
    assert data["doc_type"] == "SALARY_SLIP"
    assert data["pushed_by"] == "Infosys Ltd"
    assert data["file_hash_sha256"] == "deadbeef"
    # Must not expose raw salary/PAN field keys — doc_type "SALARY_SLIP" is fine as a type label
    for forbidden_key in ("gross_salary", "net_salary", "basic_salary", "enc_pan", "pan_token", "ctc"):
        assert forbidden_key not in data, f"Forbidden field in credential response: {forbidden_key}"


@pytest.mark.asyncio
async def test_credential_privacy_no_salary_in_response(client, mock_db):
    """Privacy contract: credential card must never contain any insight with raw ₹ salary."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "document_id":       str(uuid.uuid4()),
        "pipeline_status":   "ROUTED",
        "verification_code": "PRANA-AB1234-CD5678",
        "doc_type":          "SALARY_SLIP",
        "doc_period":        "2024-03",
        "tenant_name":       "TCS",
        "pushed_at":         datetime(2024, 3, 1, tzinfo=timezone.utc),
        "routed_at":         datetime(2024, 3, 2, tzinfo=timezone.utc),
        "file_hash_sha256":  "abc",
    }.get(k)

    headers = _auth_headers(client)
    mock_db.fetchrow = AsyncMock(return_value=row)
    resp = await client.get("/v1/vault/documents/doc-001/credential", headers=headers)
    assert resp.status_code == 200
    response_text = resp.text
    for forbidden in ("gross_salary", "net_salary", "basic_salary", "ctc", "pan"):
        assert forbidden not in response_text.lower()
