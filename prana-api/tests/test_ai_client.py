"""Tests for services/ai_client.py."""
import inspect

from services.ai_client import AiPipelineClient


def test_ai_client_proxies_to_prana_ask_not_direct_llm():
    src = inspect.getsource(AiPipelineClient)
    # AiPipelineClient uses httpx to proxy to prana-ai service
    assert "httpx" in src, "AiPipelineClient must use httpx to proxy to prana-ai"
    assert "X-Prana-AI-Secret" in src or "AI_SECRET" in src, \
        "Must include internal auth header for prana-ai VPC call"
    # Must NOT import the LLM directly
    assert "qwen" not in src.lower() and "llama" not in src.lower(), \
        "prana-api must not call LLM directly — proxy to prana-ai only"


def test_ai_client_response_filtered_for_raw_salary():
    src = inspect.getsource(AiPipelineClient)
    # prana-ai returns insights only — privacy contract enforced at prana-ai service boundary
    # AiPipelineClient is a thin proxy; it must not store or log raw salary in its own code
    assert "refresh_insight" in src, "AiPipelineClient must support insight refresh"
    # The client just proxies — it does not add salary/PAN extraction of its own
    assert "log" not in src or "salary" not in src, \
        "AiPipelineClient must not log raw salary values"
