"""
Ask PRANA privacy guard tests.

Verifies that the post-process guard in AskService blocks any LLM response
that contains raw rupee amounts, Rs. amounts, or PAN patterns.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from ask_service import AskService


_EMP_ID = UUID("aaaabbbb-cccc-dddd-eeee-ffffffffffff")

SAFE_RESPONSE = "Your salary has grown by approximately 12% year-on-year, placing you around the 70th percentile in your sector."
RUPEE_RESPONSE = "Your gross salary is ₹95,000 per month."
RS_RESPONSE = "You earned Rs. 1,20,000 as bonus last year."
PAN_RESPONSE = "Your PAN number is ABCDE1234F as per your Form 16."


def _make_svc(llm_response: str) -> AskService:
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=llm_response)

    ctx = AsyncMock()
    ctx.build = AsyncMock(return_value="Career context: engineer at Infosys since 2021.")

    return AskService(llm=llm, context_builder=ctx)


@pytest.mark.asyncio
async def test_safe_response_passes_through():
    svc = _make_svc(SAFE_RESPONSE)
    result = await svc.answer(_EMP_ID, "How has my salary grown?")
    assert result == SAFE_RESPONSE


@pytest.mark.asyncio
async def test_rupee_amount_blocked():
    svc = _make_svc(RUPEE_RESPONSE)
    result = await svc.answer(_EMP_ID, "What is my salary?")
    assert "unable" in result.lower() or "can't" in result.lower() or "cannot" in result.lower()
    assert "₹95,000" not in result
    assert "95,000" not in result


@pytest.mark.asyncio
async def test_rs_amount_blocked():
    svc = _make_svc(RS_RESPONSE)
    result = await svc.answer(_EMP_ID, "What was my bonus?")
    assert "Rs." not in result
    assert "1,20,000" not in result


@pytest.mark.asyncio
async def test_pan_pattern_blocked():
    svc = _make_svc(PAN_RESPONSE)
    result = await svc.answer(_EMP_ID, "What is my PAN?")
    assert "ABCDE1234F" not in result


@pytest.mark.asyncio
async def test_multiple_sensitive_patterns_all_blocked():
    """Response with multiple violations must all be blocked, not partially returned."""
    combined = f"{RUPEE_RESPONSE} Also your PAN is ABCDE1234F."
    svc = _make_svc(combined)
    result = await svc.answer(_EMP_ID, "Give me all my details")
    assert "₹" not in result
    assert "ABCDE1234F" not in result


@pytest.mark.asyncio
async def test_context_build_called_with_employee_id():
    """ContextBuilder must be called with the JWT employee_user_id."""
    ctx = AsyncMock()
    ctx.build = AsyncMock(return_value="context")
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=SAFE_RESPONSE)

    svc = AskService(llm=llm, context_builder=ctx)
    await svc.answer(_EMP_ID, "How many jobs have I had?")

    ctx.build.assert_called_once()
    called_id = ctx.build.call_args[0][0]
    assert called_id == _EMP_ID


@pytest.mark.asyncio
async def test_empty_query_handled_gracefully():
    svc = _make_svc(SAFE_RESPONSE)
    result = await svc.answer(_EMP_ID, "")
    assert isinstance(result, str)
    assert len(result) > 0
