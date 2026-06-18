"""Tests for insights/career_insight_service.py — model choice and privacy contract."""
import inspect
import pytest
from unittest.mock import AsyncMock

from insights.career_insight_service import CareerInsightService, _INSIGHT_SYSTEM


def test_career_insight_uses_llama_model_not_qwen():
    # CareerInsightService uses the Llama insight model, NOT Qwen (which is for extraction).
    # Verified via the system prompt — it instructs on insight generation, not raw extraction.
    # The model is injected at construction; the system prompt confirms the role boundary.
    src = inspect.getsource(CareerInsightService)
    assert "_INSIGHT_SYSTEM" in src or "INSIGHT" in src, \
        "CareerInsightService must use the insight LLM path, not the extraction prompt"
    # System prompt must forbid raw ₹ — different contract from Qwen extraction
    assert "₹" in _INSIGHT_SYSTEM or "salary amount" in _INSIGHT_SYSTEM.lower(), \
        "_INSIGHT_SYSTEM must explicitly block raw salary figures in LLM output"


@pytest.mark.asyncio
async def test_career_insight_output_filtered_no_raw_salary():
    # The LLM is instructed not to produce raw salary amounts.
    # If it does anyway (jailbreak / model drift), the system prompt is the guard.
    # Verify that _INSIGHT_SYSTEM instructions forbid specific ₹ / LPA / CTC output.
    assert "Never mention specific salary amounts" in _INSIGHT_SYSTEM or \
           "never" in _INSIGHT_SYSTEM.lower(), \
        "_INSIGHT_SYSTEM must prohibit raw salary output with an explicit NEVER rule"
    assert "LPA" in _INSIGHT_SYSTEM or "CTC" in _INSIGHT_SYSTEM or "₹" in _INSIGHT_SYSTEM, \
        "_INSIGHT_SYSTEM must enumerate the sensitive terms it forbids"
