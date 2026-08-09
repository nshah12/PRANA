"""
SkillGapService — designation-progression MVP (SkillGapWorkflow).

Deliberately modest scope: no skills taxonomy exists anywhere in the schema,
so this is NOT a comparison against stored market/taxonomy data — just an LLM
synthesis of plausible skills/growth areas from the employee's career-letter
progression. Reads the same career_event rows as career_narrative_service.py
(which by construction only contains letter-derived rows — see
pipeline/stage06_route.py's _doc_type_to_event, which maps SALARY_SLIP/
FORM_16/PF_ACKNOWLEDGEMENT to None so they never produce a row).

UI copy must frame this as "career growth suggestions," never "skill gap
analysis" — the feature is more modest than its workflow class name implies.

Privacy contract: only designation/grade/event_type reach the LLM.
career_event.ctc_annual (encrypted raw ₹) is never selected, never passed.

Cross-employee_master rule (prana-db/CLAUDE.md): resolved to the
person-level employee_user_id via subquery, then career_event matched
across ALL that person's employee_master rows — same as career_narrative_service.py.
"""
from __future__ import annotations

import json
import logging

import asyncpg

from llm_client import LLMClient

log = logging.getLogger(__name__)

_SKILL_GAP_SYSTEM = """You are a career growth assistant for PRANA.
Given an employee's designation/grade progression, suggest skills plausibly
evidenced by that progression and 2-3 general next-step growth areas.
RULES:
- Never mention specific salary amounts (₹, LPA, CTC, etc.)
- Base suggestions only on general professional knowledge — you have no
  access to any skills database or market benchmark for this employee
- Be encouraging and specific to the designation/grade given
- Write in second person ("You could grow by…")
- Output plain text only — no JSON, no markdown
"""


class SkillGapService:

    def __init__(self, db: asyncpg.Connection, llm_client: LLMClient):
        self._db = db
        self._llm = llm_client

    async def build_skill_gap(self, *, employee_uuid: str) -> dict:
        rows = await self._db.fetch(
            """
            SELECT event_type, designation, grade
            FROM career_event
            WHERE employee_user_id = (
              SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1
            )
            ORDER BY event_date ASC
            """,
            employee_uuid,
        )

        latest_designation = next(
            (r["designation"] for r in reversed(rows) if r["designation"]), None,
        )
        suggestions = await self._generate_suggestions(rows, latest_designation)
        return {"insights": {
            "suggestions": suggestions,
            "based_on_designation": latest_designation,
        }}

    async def _generate_suggestions(self, rows: list, latest_designation: str | None) -> str:
        if not rows:
            return "Add your career documents to start receiving personalised growth suggestions."

        progression = [
            {"event_type": r["event_type"], "designation": r["designation"], "grade": r["grade"]}
            for r in rows
        ]
        user_msg = (
            f"Career progression (chronological): {json.dumps(progression, ensure_ascii=False)}\n\n"
            "Suggest skills and growth areas for this employee."
        )
        try:
            return await self._llm.complete(
                system=_SKILL_GAP_SYSTEM,
                user=user_msg,
                max_tokens=200,
                temperature=0.3,
            )
        except Exception as exc:
            log.warning("LLM skill gap generation failed: %s", exc)
            return _fallback_suggestions(latest_designation)


def _fallback_suggestions(latest_designation: str | None) -> str:
    if not latest_designation:
        return "Add your career documents to start receiving personalised growth suggestions."
    return (
        f"As a {latest_designation}, consider building skills in stakeholder "
        "communication, mentoring, and domain specialisation to support your next step."
    )
