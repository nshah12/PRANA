"""Tests for manifest/manifest_client.py — ManifestClient HTTP + cache behaviour."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from manifest.manifest_client import ManifestClient, ManifestData, MANIFEST_CACHE_TTL

BASE_URL = "http://prana-api.prod.internal:8000"
TOKEN = "test-internal-token"

MANIFEST_PAYLOAD = {
    "manifest_id":            "mfst-001",
    "doc_type":               "SALARY_SLIP",
    "required_fields":        ["employee_name", "month", "employer_name"],
    "identity_fields":        ["employee_name"],
    "optional_fields":        ["department"],
    "classification_signals": [["employee_name", "month"], ["gross_salary"]],
    "confidence_threshold":   0.80,
    "supported_formats":      ["pdf", "jpeg"],
    "is_tenant_override":     False,
}


def _make_client() -> ManifestClient:
    return ManifestClient(prana_api_base_url=BASE_URL, internal_token=TOKEN)


def _mock_http_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── resolve() — single manifest fetch ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_returns_manifest_data():
    """resolve() fetches from prana-api internal endpoint and returns ManifestData."""
    client = _make_client()

    mock_resp = _mock_http_response({"manifest": MANIFEST_PAYLOAD})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        result = await client.resolve("tenant-1", "SALARY_SLIP")

    assert isinstance(result, ManifestData)
    assert result.doc_type == "SALARY_SLIP"
    assert result.confidence_threshold == 0.80
    assert "employee_name" in result.required_fields
    assert result.format_supported("pdf") is True
    assert result.format_supported("docx") is False


@pytest.mark.asyncio
async def test_resolve_calls_correct_url():
    """resolve() constructs the correct internal URL with tenant_id and doc_type."""
    client = _make_client()
    captured_url = {}

    mock_resp = _mock_http_response({"manifest": MANIFEST_PAYLOAD})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    async def _get(url, **kwargs):
        captured_url["url"] = url
        return mock_resp

    mock_http.get = _get

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        await client.resolve("tenant-abc", "FORM_16")

    assert captured_url["url"] == f"{BASE_URL}/internal/manifests/tenant-abc/FORM_16"


@pytest.mark.asyncio
async def test_resolve_sends_auth_header():
    """resolve() attaches the internal token in Authorization header."""
    client = _make_client()
    captured_headers = {}

    mock_resp = _mock_http_response({"manifest": MANIFEST_PAYLOAD})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    async def _get(url, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return mock_resp

    mock_http.get = _get

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        await client.resolve("tenant-1", "SALARY_SLIP")

    assert captured_headers.get("Authorization") == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_resolve_404_raises_value_error():
    """resolve() raises ValueError when prana-api returns 404 (unknown doc_type)."""
    client = _make_client()

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status = MagicMock()
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(ValueError, match="No manifest"):
            await client.resolve("tenant-1", "UNKNOWN_TYPE")


# ── Cache behaviour ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_caches_result():
    """Second call for the same (tenant, doc_type) must not make a second HTTP call."""
    client = _make_client()
    call_count = 0

    mock_resp = _mock_http_response({"manifest": MANIFEST_PAYLOAD})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    async def _get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_resp

    mock_http.get = _get

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        await client.resolve("tenant-1", "SALARY_SLIP")
        await client.resolve("tenant-1", "SALARY_SLIP")

    assert call_count == 1, "Expected cache hit on second call — got HTTP request instead"


@pytest.mark.asyncio
async def test_invalidate_clears_cache():
    """invalidate() causes the next resolve() to fetch fresh from HTTP."""
    client = _make_client()
    call_count = 0

    mock_resp = _mock_http_response({"manifest": MANIFEST_PAYLOAD})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    async def _get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_resp

    mock_http.get = _get

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        await client.resolve("tenant-1", "SALARY_SLIP")
        client.invalidate("tenant-1", "SALARY_SLIP")
        await client.resolve("tenant-1", "SALARY_SLIP")

    assert call_count == 2, "Expected re-fetch after invalidate()"


# ── list_all() ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_all_returns_list_of_manifest_data():
    """list_all() fetches /internal/manifests/{tenant} and returns a list."""
    client = _make_client()

    mock_resp = _mock_http_response({"items": [MANIFEST_PAYLOAD, {**MANIFEST_PAYLOAD, "doc_type": "FORM_16", "manifest_id": "mfst-002"}]})
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("manifest.manifest_client.httpx.AsyncClient", return_value=mock_http):
        results = await client.list_all("tenant-1")

    assert len(results) == 2
    assert all(isinstance(r, ManifestData) for r in results)
    assert {r.doc_type for r in results} == {"SALARY_SLIP", "FORM_16"}


# ── ManifestData helpers ──────────────────────────────────────────────────────

def test_score_against_all_signals_present():
    """score_against returns 1.0 when all classification signals are satisfied."""
    m = ManifestData(
        manifest_id="x", doc_type="SALARY_SLIP",
        required_fields=["employee_name"], identity_fields=["employee_name"],
        optional_fields=[], confidence_threshold=0.8,
        classification_signals=[["employee_name", "month"], ["employer_name"]],
        supported_formats=["pdf"],
    )
    fields = {"employee_name": "Nilesh Shah", "month": "2024-03", "employer_name": "Infosys"}
    assert m.score_against(fields) == 1.0


def test_score_against_no_signals_returns_zero():
    """score_against returns 0.0 when manifest has no classification_signals."""
    m = ManifestData(
        manifest_id="x", doc_type="FORM_16",
        required_fields=[], identity_fields=[],
        optional_fields=[], confidence_threshold=0.75,
        classification_signals=[],
        supported_formats=["pdf"],
    )
    assert m.score_against({"employee_name": "test"}) == 0.0


def test_format_supported_case_insensitive():
    """format_supported() is case-insensitive."""
    m = ManifestData(
        manifest_id="x", doc_type="T", required_fields=[], identity_fields=[],
        optional_fields=[], confidence_threshold=0.8,
        classification_signals=[], supported_formats=["pdf", "JPEG"],
    )
    assert m.format_supported("PDF") is True
    assert m.format_supported("jpeg") is True
    assert m.format_supported("docx") is False
