"""Tests for services/ai_client.py — proxy shape + structured error handling."""
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from services.ai_client import AiPipelineClient


# ── Existing proxy tests ──────────────────────────────────────────────────────

def test_ai_client_proxies_to_prana_ask_not_direct_llm():
    src = inspect.getsource(AiPipelineClient)
    assert "httpx" in src, "AiPipelineClient must use httpx to proxy to prana-ai"
    assert "X-Prana-AI-Secret" in src or "AI_SECRET" in src, \
        "Must include internal auth header for prana-ai VPC call"
    assert "qwen" not in src.lower() and "llama" not in src.lower(), \
        "prana-api must not call LLM directly — proxy to prana-ai only"


def test_ai_client_response_filtered_for_raw_salary():
    src = inspect.getsource(AiPipelineClient)
    assert "refresh_insight" in src, "AiPipelineClient must support insight refresh"
    assert "log" not in src or "salary" not in src, \
        "AiPipelineClient must not log raw salary values"


# ── Retryable error handling — RED tests ─────────────────────────────────────

def _make_response(status_code: int, body: dict) -> httpx.Response:
    """Build a fake httpx.Response for mocking."""
    content = json.dumps(body).encode()
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=content,
        request=httpx.Request("POST", "http://prana-ai.internal/pipeline/scan"),
    )


def test_check_response_exists_on_ai_client():
    """AiPipelineClient must have a _check_response helper (all methods use it)."""
    assert hasattr(AiPipelineClient, "_check_response"), \
        "_check_response method is missing from AiPipelineClient"


def test_check_response_non_retryable_raises_application_error():
    """422 with retryable=false must raise ApplicationError(non_retryable=True)."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    resp = _make_response(422, {
        "error": "S04_EXTRACT_PASSWORD_PROTECTED",
        "stage": "stage04",
        "message": "PDF is password-protected",
        "retryable": False,
    })
    with pytest.raises(ApplicationError) as exc_info:
        client._check_response(resp)
    assert exc_info.value.non_retryable is True
    assert "S04_EXTRACT_PASSWORD_PROTECTED" in str(exc_info.value)


def test_check_response_retryable_raises_regular_exception():
    """422 with retryable=true must raise a non-ApplicationError exception so Temporal retries."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    resp = _make_response(422, {
        "error": "S04_EXTRACT_LLM_TIMEOUT",
        "stage": "stage04",
        "message": "LLM timed out",
        "retryable": True,
    })
    with pytest.raises(Exception) as exc_info:
        client._check_response(resp)
    # Must NOT be ApplicationError(non_retryable=True)
    if isinstance(exc_info.value, ApplicationError):
        assert exc_info.value.non_retryable is False, \
            "Retryable 422 must not produce non_retryable=True ApplicationError"


def test_check_response_other_4xx_raises_http_status_error():
    """Non-422 4xx/5xx responses must raise httpx.HTTPStatusError (unchanged behaviour)."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    for status in (400, 401, 500, 503):
        resp = _make_response(status, {"error": "INTERNAL_ERROR", "detail": "..."})
        with pytest.raises(httpx.HTTPStatusError):
            client._check_response(resp)


def test_check_response_2xx_does_not_raise():
    """Successful responses must not raise."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    resp = _make_response(200, {"status": "ok", "extracted_fields": {}})
    client._check_response(resp)  # must not raise
    resp204 = httpx.Response(
        status_code=204,
        content=b"",
        request=httpx.Request("POST", "http://prana-ai.internal/pipeline/route"),
    )
    client._check_response(resp204)  # must not raise


def test_check_response_csam_is_non_retryable():
    """CSAM detection must always produce non_retryable=True ApplicationError."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    resp = _make_response(422, {
        "error": "S03_SCAN_CSAM_DETECTED",
        "stage": "stage03",
        "message": "CSAM detected — mandatory legal hold",
        "retryable": False,
    })
    with pytest.raises(ApplicationError) as exc_info:
        client._check_response(resp)
    assert exc_info.value.non_retryable is True


def test_check_response_cross_tenant_is_non_retryable():
    """Cross-tenant violation must produce non_retryable=True ApplicationError."""
    client = AiPipelineClient.__new__(AiPipelineClient)
    resp = _make_response(422, {
        "error": "S05_RESOLVE_CROSS_TENANT",
        "stage": "stage05",
        "message": "pan_token belongs to different tenant",
        "retryable": False,
    })
    with pytest.raises(ApplicationError) as exc_info:
        client._check_response(resp)
    assert exc_info.value.non_retryable is True


def test_all_methods_call_check_response():
    """Every method that calls prana-ai must use _check_response (not raw raise_for_status)."""
    src = inspect.getsource(AiPipelineClient)
    # After the change, raise_for_status() calls must be gone from method bodies;
    # all error handling goes through _check_response
    assert "_check_response" in src, \
        "AiPipelineClient must have _check_response centralising error handling"
    # scan, extract, resolve, route, raise_exception, refresh_insight must all use it
    for method in ("scan", "extract", "resolve", "route", "raise_exception", "refresh_insight"):
        method_src = inspect.getsource(getattr(AiPipelineClient, method))
        assert "_check_response" in method_src, \
            f"AiPipelineClient.{method} must call self._check_response(resp)"
