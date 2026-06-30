"""Tests for routers/public.py and the /health endpoint."""
from unittest.mock import AsyncMock, MagicMock
import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_public_endpoints_require_no_auth(client):
    # /public/contact can be called without any auth token
    resp = await client.post(
        "/public/contact",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "message": "Hello PRANA",
            "company": "Test Corp",
        },
    )
    # 201 created or 500 (DB mock returns None but no auth required)
    assert resp.status_code != 401, "Public contact endpoint must not require auth"
    assert resp.status_code != 403, "Public contact endpoint must not require auth"


# ── Credential verification tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_rejects_malformed_code(client):
    """Codes that don't match PRANA-XXXXXX-XXXXXX shape return 400."""
    for bad_code in ["NOTPRANA", "PRANA-123", "prana-ABC123-DEF456"]:
        resp = await client.get(f"/public/verify/{bad_code}")
        assert resp.status_code == 400, f"Expected 400 for {bad_code}"


@pytest.mark.asyncio
async def test_verify_unknown_code_returns_404(client, mock_db):
    """Valid format but code not in DB → 404."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = await client.get("/public/verify/PRANA-ABC123-XYZ789")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_verify_returns_metadata_only(client, mock_db):
    """Happy path: returns verified=True and metadata — no salary, no full PAN."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    doc_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    emp_uuid = str(uuid.uuid4())

    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "document_id":        doc_id,
        "doc_type":           "FORM_16",
        "doc_period":         "FY:2023-24",
        "pushed_at":          datetime(2024, 5, 1, tzinfo=timezone.utc),
        "routed_at":          datetime(2024, 5, 2, tzinfo=timezone.utc),
        "file_hash_sha256":   "abc123def456",
        "verification_code":  "PRANA-ABC123-XYZ789",
        "tenant_id":          tenant_id,
        "employee_uuid":      emp_uuid,
        "is_deleted":         False,
        "company_name":       "InfyTech Ltd",
        "full_name":          "Nilesh Shah",
    }.get(k)

    mock_db.fetchrow = AsyncMock(return_value=row)
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.get("/public/verify/PRANA-ABC123-XYZ789")
    assert resp.status_code == 200
    data = resp.json()

    assert data["verified"] is True
    assert data["doc_type"] == "FORM_16"
    assert data["pushed_by"] == "InfyTech Ltd"
    assert data["file_hash_sha256"] == "abc123def456"

    # Privacy: employee display must be first-initial + last name only
    assert data["employee_display"] == "N. Shah"

    # Privacy: must not contain any salary or PAN field
    body_str = str(data)
    for forbidden in ("salary", "pan", "ctc", "₹"):
        assert forbidden.lower() not in body_str.lower()


@pytest.mark.asyncio
async def test_verify_no_auth_required(client, mock_db):
    """Verification endpoint must be accessible without Authorization header."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = await client.get("/public/verify/PRANA-ABC123-XYZ789")
    assert resp.status_code != 401
    assert resp.status_code != 403
