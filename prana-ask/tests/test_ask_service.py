"""Tests for ask_service.py — privacy filter and employee scoping."""
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from ask_service import AskService, _BLOCK_PATTERNS

_EMP_ID = UUID("aaaabbbb-cccc-dddd-eeee-ffffffffffff")


def _make_svc(llm_response: str) -> AskService:
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=llm_response)
    ctx = AsyncMock()
    ctx.build = AsyncMock(return_value="Career context: engineer at Infosys since 2021.")
    return AskService(llm=llm, context_builder=ctx)


def test_ask_service_privacy_filter_blocks_raw_salary_in_response():
    rupee = "Your gross salary is ₹95,000 per month."
    matches = [p for p in _BLOCK_PATTERNS if p.search(rupee)]
    assert matches, "No block pattern matches a raw rupee amount — privacy guard is broken"


def test_ask_service_privacy_filter_blocks_pan_in_response():
    pan = "Your PAN number is ABCDE1234F as per your Form 16."
    matches = [p for p in _BLOCK_PATTERNS if p.search(pan)]
    assert matches, "No block pattern matches a PAN string — privacy guard is broken"


@pytest.mark.asyncio
async def test_ask_service_qdrant_query_includes_employee_user_id_filter():
    # ContextBuilder.build must be called with the JWT employee_user_id so
    # it scopes the Qdrant collection to that employee's data only.
    ctx = AsyncMock()
    ctx.build = AsyncMock(return_value="context")
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Your career spans 5 years.")

    svc = AskService(llm=llm, context_builder=ctx)
    await svc.answer(_EMP_ID, "How long have I worked?")

    ctx.build.assert_called_once()
    assert ctx.build.call_args[0][0] == _EMP_ID, \
        "context_builder.build must receive JWT employee_user_id as first arg"
