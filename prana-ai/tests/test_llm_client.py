"""
Tests for llm_client.py's usage-logging hook.

Design: LLMClient.complete() keeps returning a plain str (unchanged) so none
of its 4 existing callers (extraction_service.py, career_insight_service.py,
pipeline/stage04_extract.py x2) need to change. An optional usage_logger
callback receives the OpenAI-compatible response's `usage` block after each
call, best-effort (a logging failure must never break extraction).
"""
from unittest.mock import AsyncMock

import httpx
import pytest

from llm_client import LLMClient


def _mock_transport(usage: dict | None = None):
    payload = {"choices": [{"message": {"content": "hello"}}]}
    if usage is not None:
        payload["usage"] = usage

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_complete_still_returns_plain_string(monkeypatch):
    """The return type must stay str — no caller should need updating."""
    client = LLMClient(base_url="http://fake", model="test-model")
    transport = _mock_transport({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    _RealAsyncClient = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))

    result = await client.complete(system="s", user="u")

    assert result == "hello"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_complete_calls_usage_logger_with_token_counts(monkeypatch):
    logger = AsyncMock()
    client = LLMClient(base_url="http://fake", model="test-model", usage_logger=logger)
    transport = _mock_transport({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    _RealAsyncClient = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))

    await client.complete(system="s", user="u")

    logger.assert_called_once()
    usage = logger.call_args.args[0]
    assert usage["model"] == "test-model"
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_complete_skips_logging_gracefully_when_usage_missing(monkeypatch):
    """Some OpenAI-compatible backends may omit `usage` — must not crash."""
    logger = AsyncMock()
    client = LLMClient(base_url="http://fake", model="test-model", usage_logger=logger)
    transport = _mock_transport(usage=None)
    _RealAsyncClient = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))

    result = await client.complete(system="s", user="u")

    assert result == "hello"
    logger.assert_called_once()
    usage = logger.call_args.args[0]
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0


@pytest.mark.asyncio
async def test_complete_survives_usage_logger_failure(monkeypatch):
    """A broken logger (e.g. DB down) must never break extraction."""
    logger = AsyncMock(side_effect=Exception("db down"))
    client = LLMClient(base_url="http://fake", model="test-model", usage_logger=logger)
    transport = _mock_transport({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
    _RealAsyncClient = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))

    result = await client.complete(system="s", user="u")

    assert result == "hello"  # extraction result still returned despite logger failure


@pytest.mark.asyncio
async def test_complete_works_with_no_usage_logger_configured():
    """Default construction (no usage_logger) must behave exactly as before."""
    client = LLMClient(base_url="http://fake", model="test-model")
    assert client._usage_logger is None
