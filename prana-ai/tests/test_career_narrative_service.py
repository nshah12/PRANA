"""Tests for insights/career_narrative_service.py (new) — CareerInsightWorkflow.

Full-history aggregated career narrative — different from
career_insight_service.py's per-document snippet (that's InsightRefreshWorkflow,
already working). Reads career_event rows (designation/grade/event_type/
event_date/insight_text) across ALL of an employee's employee_master rows
(multi-org employees have multiple rows — prana-db/CLAUDE.md's career-query
rule) — never ctc_annual, which stays encrypted and unread.
"""
from unittest.mock import AsyncMock

import pytest

from insights.career_narrative_service import CareerNarrativeService, _NARRATIVE_SYSTEM


def test_narrative_system_prompt_forbids_raw_salary():
    assert "never" in _NARRATIVE_SYSTEM.lower()
    assert "₹" in _NARRATIVE_SYSTEM or "LPA" in _NARRATIVE_SYSTEM or "CTC" in _NARRATIVE_SYSTEM


@pytest.mark.asyncio
async def test_build_narrative_queries_across_all_employee_master_rows():
    """Multi-org employees have multiple employee_master rows (one per
    tenant) — prana-db/CLAUDE.md's rule: career queries must resolve to the
    person-level anchor (employee_user_id) via a subquery from the one given
    employee_uuid, then match career_event across ALL that person's rows —
    never filter career_event by a single employee_uuid directly."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="A steady career of growth.")

    svc = CareerNarrativeService(db=db, llm_client=llm)
    await svc.build_narrative(employee_uuid="emp-1")

    sql = db.fetch.call_args.args[0]
    assert "employee_user_id" in sql
    assert "SELECT employee_user_id FROM employee_master" in sql
    assert db.fetch.call_args.args[1] == "emp-1"


@pytest.mark.asyncio
async def test_build_narrative_never_reads_ctc_annual():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "JOINED", "event_date": None, "designation": "Analyst", "grade": "L1", "insight_text": None},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Narrative.")

    svc = CareerNarrativeService(db=db, llm_client=llm)
    await svc.build_narrative(employee_uuid="emp-1")

    sql = db.fetch.call_args.args[0]
    assert "ctc_annual" not in sql
    llm_call = llm.complete.call_args
    assert "ctc_annual" not in llm_call.kwargs.get("user", "") and "ctc_annual" not in str(llm_call)


@pytest.mark.asyncio
async def test_build_narrative_returns_insights_shaped_dict():
    """Shape must match write_career_insight's expectation — a dict stored
    directly into employee_insight.insights (JSONB), same convention as
    build_market_comp's {"insights": {...}} return."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "JOINED", "event_date": None, "designation": "Analyst", "grade": "L1", "insight_text": "Started strong."},
        {"event_type": "PROMOTED", "event_date": None, "designation": "Senior Analyst", "grade": "L2", "insight_text": None},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Promoted from Analyst to Senior Analyst — strong trajectory.")

    svc = CareerNarrativeService(db=db, llm_client=llm)
    result = await svc.build_narrative(employee_uuid="emp-1")

    assert result == {"insights": {
        "narrative": "Promoted from Analyst to Senior Analyst — strong trajectory.",
        "milestones": [
            {"event_type": "JOINED", "event_date": None, "designation": "Analyst", "grade": "L1"},
            {"event_type": "PROMOTED", "event_date": None, "designation": "Senior Analyst", "grade": "L2"},
        ],
    }}


@pytest.mark.asyncio
async def test_build_narrative_falls_back_when_llm_fails():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"event_type": "JOINED", "event_date": None, "designation": "Analyst", "grade": "L1", "insight_text": None},
    ])
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=Exception("LLM down"))

    svc = CareerNarrativeService(db=db, llm_client=llm)
    result = await svc.build_narrative(employee_uuid="emp-1")

    assert result["insights"]["narrative"]  # non-empty fallback text, not a crash
    assert "milestones" in result["insights"]


@pytest.mark.asyncio
async def test_build_narrative_empty_history():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="No career history yet.")

    svc = CareerNarrativeService(db=db, llm_client=llm)
    result = await svc.build_narrative(employee_uuid="emp-1")

    assert result["insights"]["milestones"] == []
