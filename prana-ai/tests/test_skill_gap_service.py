"""Tests for insights/skill_gap_service.py (new) — SkillGapWorkflow.

MVP scope (deliberately modest — no skills taxonomy exists anywhere in the
schema, so this is NOT a comparison against stored market/taxonomy data).
Feeds the employee's designation/grade progression — sourced from
career_event, which by construction only ever contains rows for career-letter
document types (OFFER_LETTER/APPOINTMENT_LETTER/PROMOTION_LETTER/
INCREMENT_LETTER/JOINING_LETTER/RELIEVING_LETTER/EXPERIENCE_LETTER — see
prana-ai/pipeline/stage06_route.py's _doc_type_to_event, which maps
SALARY_SLIP/FORM_16/PF_ACKNOWLEDGEMENT to None so they never get a row) — to
an LLM, asking for skills plausibly evidenced by that progression and general
next-step growth areas. General LLM world-knowledge synthesis, not a lookup
against any stored taxonomy. UI copy must call this "career growth
suggestions," not "skill gap analysis" — the plan's own honesty framing.
"""
from unittest.mock import AsyncMock

import pytest

from insights.skill_gap_service import SkillGapService, _SKILL_GAP_SYSTEM


def test_skill_gap_system_prompt_forbids_raw_salary():
    assert "never" in _SKILL_GAP_SYSTEM.lower()
    assert "₹" in _SKILL_GAP_SYSTEM or "LPA" in _SKILL_GAP_SYSTEM or "CTC" in _SKILL_GAP_SYSTEM


def test_skill_gap_system_prompt_frames_this_as_general_synthesis_not_taxonomy_lookup():
    """The plan's own honesty framing: this is NOT a comparison against a
    stored skills taxonomy or market data — no such taxonomy exists in the
    schema. The prompt must not claim otherwise to the LLM or imply
    authoritative benchmarking."""
    assert "taxonomy" not in _SKILL_GAP_SYSTEM.lower()
    assert "market data" not in _SKILL_GAP_SYSTEM.lower()


@pytest.mark.asyncio
async def test_build_skill_gap_queries_across_all_employee_master_rows():
    """Same cross-employee_master rule as career_narrative_service.py —
    multi-org employees have multiple employee_master rows."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Keep building your leadership skills.")

    svc = SkillGapService(db=db, llm_client=llm)
    await svc.build_skill_gap(employee_uuid="emp-1")

    sql = db.fetch.call_args.args[0]
    assert "employee_user_id" in sql
    assert "SELECT employee_user_id FROM employee_master" in sql
    assert db.fetch.call_args.args[1] == "emp-1"


@pytest.mark.asyncio
async def test_build_skill_gap_never_reads_ctc_annual():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "PROMOTED", "designation": "Senior Analyst", "grade": "L2"},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Suggestions.")

    svc = SkillGapService(db=db, llm_client=llm)
    await svc.build_skill_gap(employee_uuid="emp-1")

    sql = db.fetch.call_args.args[0]
    assert "ctc_annual" not in sql
    llm_call = llm.complete.call_args
    assert "ctc_annual" not in str(llm_call)


@pytest.mark.asyncio
async def test_build_skill_gap_returns_insights_shaped_dict():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "JOINED", "designation": "Analyst", "grade": "L1"},
        {"event_type": "PROMOTED", "designation": "Senior Analyst", "grade": "L2"},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Suggested growth: stakeholder management, mentoring.")

    svc = SkillGapService(db=db, llm_client=llm)
    result = await svc.build_skill_gap(employee_uuid="emp-1")

    assert result == {"insights": {
        "suggestions": "Suggested growth: stakeholder management, mentoring.",
        "based_on_designation": "Senior Analyst",
    }}


@pytest.mark.asyncio
async def test_build_skill_gap_falls_back_when_llm_fails():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "JOINED", "designation": "Analyst", "grade": "L1"},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=Exception("LLM down"))

    svc = SkillGapService(db=db, llm_client=llm)
    result = await svc.build_skill_gap(employee_uuid="emp-1")

    assert result["insights"]["suggestions"]  # non-empty fallback text, not a crash


@pytest.mark.asyncio
async def test_build_skill_gap_empty_history():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="unused")

    svc = SkillGapService(db=db, llm_client=llm)
    result = await svc.build_skill_gap(employee_uuid="emp-1")

    assert result["insights"]["based_on_designation"] is None
    assert result["insights"]["suggestions"]
