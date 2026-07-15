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


@pytest.mark.asyncio
async def test_v1_public_mirror_serves_same_handlers_as_public(client, mock_db):
    """public.router is mounted twice — /public (legacy) and /v1/public (versioned,
    per api-versioning.md). Both must resolve to the identical handler/response."""
    mock_db.fetchrow.return_value = None  # both calls hit the same "not found" path identically
    r1 = await client.get("/public/verify/PRANA-123456-789012")
    r2 = await client.get("/v1/public/verify/PRANA-123456-789012")
    assert r1.status_code == r2.status_code == 404
    assert r1.json() == r2.json()

    r1 = await client.get("/public/qr/PRANA-123456-789012")
    r2 = await client.get("/v1/public/qr/PRANA-123456-789012")
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content


@pytest.mark.asyncio
async def test_contact_inquiries_no_longer_served_from_public_router(client):
    """The 3 PA-only reads relocated to /admin/* (routers/pa_admin.py) — they
    must not still be reachable under /public or /v1/public."""
    for path in ["/public/contact-inquiries", "/v1/public/contact-inquiries"]:
        resp = await client.get(path)
        assert resp.status_code == 404


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


# ── QR code endpoint tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qr_malformed_code_returns_400(client):
    """Non-PRANA codes must be rejected before image generation."""
    for bad in ["notprana", "PRANA-123", "prana-ABC123-DEF456"]:
        resp = await client.get(f"/public/qr/{bad}")
        assert resp.status_code == 400, f"Expected 400 for {bad}"


@pytest.mark.asyncio
async def test_qr_valid_code_returns_png(client):
    """Valid PRANA code returns a PNG image (no auth required)."""
    resp = await client.get("/public/qr/PRANA-ABC123-XYZ789")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


# ── Rate limiting tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_rate_limited_after_threshold(client, mock_db):
    """
    The /public/verify endpoint must rate-limit callers to ≤10 req/min per IP.
    The 11th request from the same IP in a minute must return 429.
    RED: fails until slowapi limiter is wired to this endpoint.
    """
    mock_db.fetchrow = AsyncMock(return_value=None)  # 404s are fine — rate limit fires first

    responses = []
    for _ in range(11):
        r = await client.get(
            "/public/verify/PRANA-ABC123-XYZ789",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        responses.append(r.status_code)

    assert 429 in responses, (
        "After 10 requests/min, /public/verify must return 429. "
        "Rate limiting is not wired up yet."
    )


# ── Async access log via Kafka ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_access_log_published_to_kafka_not_written_to_db(client, mock_db, mock_kafka):
    """
    Successful verification must publish a DOC_ACCESSED event to Kafka (AuditConsumer
    writes the document_access_log row), NOT write directly to document_access_log.
    A synchronous DB write in the public HTTP path blocks under load and adds latency.
    RED: fails until public.py switches to kafka_producer.publish().
    """
    import uuid
    from datetime import datetime, timezone

    doc_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    emp_uuid = str(uuid.uuid4())

    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "document_id": doc_id, "doc_type": "FORM_16", "doc_period": "FY:2023-24",
        "pushed_at": datetime(2024, 5, 1, tzinfo=timezone.utc),
        "routed_at": datetime(2024, 5, 2, tzinfo=timezone.utc),
        "file_hash_sha256": "abc123", "verification_code": "PRANA-ABC123-XYZ789",
        "tenant_id": tenant_id, "employee_uuid": emp_uuid,
        "is_deleted": False, "company_name": "InfyTech Ltd", "full_name": "Nilesh Shah",
    }.get(k)

    mock_db.fetchrow = AsyncMock(return_value=row)
    mock_db.execute = AsyncMock()

    resp = await client.get("/public/verify/PRANA-ABC123-XYZ789")
    assert resp.status_code == 200

    # Must call kafka_producer.doc_accessed() — AuditConsumer writes document_access_log
    mock_kafka.doc_accessed.assert_called_once()
    event = mock_kafka.doc_accessed.call_args.args[0]
    assert event.get("event_type") == "DOC_ACCESSED"
    assert event.get("access_type") == "VERIFY"
    assert event.get("access_channel") == "SHARE_LINK"

    # Must NOT write directly to document_access_log in the HTTP path
    direct_db_inserts = [
        str(c) for c in mock_db.execute.call_args_list
        if "document_access_log" in str(c).lower()
    ]
    assert not direct_db_inserts, (
        "HTTP handler must not INSERT directly into document_access_log. "
        "Use kafka_producer.doc_accessed() instead."
    )


@pytest.mark.asyncio
async def test_qr_requires_no_auth(client):
    """QR endpoint is public — must not require Authorization."""
    resp = await client.get("/public/qr/PRANA-ABC123-XYZ789")
    assert resp.status_code != 401
    assert resp.status_code != 403
