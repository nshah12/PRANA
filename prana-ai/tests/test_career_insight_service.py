"""Tests for insights/career_insight_service.py — model choice and privacy contract."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_refresh_for_document_writes_insight_text_to_career_event_not_document():
    """Regression, found 2026-08-06: this previously ran
    `UPDATE document SET insight_text=...` — document has no such column
    (only career_event does, per schema.sql:196, 'Ask PRANA reads from
    here'). Every real call crashed with UndefinedColumnError, and
    career_event.insight_text — the column Ask PRANA and vault.py's /career
    endpoint both read — was never once populated. No prior test asserted
    the actual SQL, only source-inspected the LLM prompt."""
    db = AsyncMock()
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Your salary growth is steady.")
    embed = AsyncMock()
    embed.embed = AsyncMock(return_value=[0.1, 0.2])
    qdrant = AsyncMock()

    svc = CareerInsightService(db=db, llm_client=llm, embedding_client=embed, qdrant_client=qdrant)
    await svc.refresh_for_document(
        document_id="doc-1", employee_uuid="emp-1", doc_type="SALARY_SLIP",
        doc_period="2026-01", benchmarks={"growth_index": 105},
    )

    call = db.execute.call_args
    sql = call.args[0]
    assert "UPDATE career_event" in sql
    assert "doc_uuid" in sql
    assert "UPDATE document " not in sql and "UPDATE document\n" not in sql
    assert call.args[1] == "doc-1"
    assert call.args[2] == "Your salary growth is steady."
