"""Phase 2 hardening tests: security headers, readiness probe, upload content-sniff."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from config import Settings


# ── Security headers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_security_headers_present_on_responses(client):
    r = await client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'none'" in r.headers.get("Content-Security-Policy", "")


# ── Readiness probe ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_readiness_ok_when_dependencies_up(client):
    client.app.state.redis.ping = AsyncMock(return_value=True)
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


@pytest.mark.asyncio
async def test_readiness_503_when_db_down(client):
    # Make the DB probe fail — readiness must report not-ready with 503 so the LB
    # stops routing traffic to this pod (finding: /health used to always say ok).
    client.app.state.db_pool.fetchval = AsyncMock(side_effect=Exception("db down"))
    client.app.state.redis.ping = AsyncMock(return_value=True)
    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["db"] == "down"


# ── CORS hardening ────────────────────────────────────────────────────────────

_ORIGINS = ["http://localhost:3000", "https://nshah12.github.io", "https://app.prana.in"]


def test_prod_cors_drops_localhost_and_github_io():
    s = Settings(app_env="production", cors_origins=_ORIGINS)
    origins = s.effective_cors_origins
    assert origins == ["https://app.prana.in"]
    assert not any("localhost" in o for o in origins)
    assert not any("github.io" in o for o in origins)


def test_dev_cors_keeps_all_origins():
    s = Settings(app_env="development", cors_origins=_ORIGINS)
    assert s.effective_cors_origins == _ORIGINS


# ── Upload content-sniff (magic bytes) ────────────────────────────────────────

def test_validate_file_rejects_non_pdf_content():
    from routers.ingest import _validate_file
    with pytest.raises(HTTPException) as e:
        _validate_file("evil.pdf", b"MZ\x90\x00 this is actually an exe")
    assert e.value.status_code == 422


def test_validate_file_accepts_real_pdf():
    from routers.ingest import _validate_file
    _validate_file("slip.pdf", b"%PDF-1.4 real pdf")  # must not raise
