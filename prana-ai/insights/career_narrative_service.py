"""
CareerNarrativeService — full-history aggregated career narrative
(CareerInsightWorkflow). Different from career_insight_service.py's
per-document snippet (InsightRefreshWorkflow, already working, writes
career_event.insight_text) — this synthesizes across an employee's ENTIRE
career_event history into one narrative + milestone list, written to
employee_insight (type CAREER) by prana-api's write_career_insight.

Privacy contract: only designation/grade/event_type/event_date/insight_text
reach the LLM. career_event.ctc_annual (encrypted raw ₹) is never selected,
never passed.

Cross-employee_master rule (prana-db/CLAUDE.md): a multi-org employee has
one employee_master row per tenant they've worked at. The input employee_uuid
is just one of those rows — resolved to the person-level employee_user_id
via a subquery, then career_event is matched across ALL that person's rows,
not filtered to the single employee_uuid given.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import asyncpg

from llm_client import LLMClient

log = logging.getLogger(__name__)

_NARRATIVE_SYSTEM = """You are a career intelligence assistant for PRANA.
Synthesize the employee's full career event history into a warm, encouraging
3-4 sentence narrative of their professional journey.
RULES:
- Never mention specific salary amounts (₹, LPA, CTC, etc.)
- Reference designations, grades, and career transitions only
- Be factual, positive, and forward-looking
- Write in second person ("Your career has grown…")
- Output plain text only — no JSON, no markdown
"""


class CareerNarrativeService:

    def __init__(self, db: asyncpg.Connection, llm_client: LLMClient):
        self._db = db
        self._llm = llm_client

    async def build_narrative(self, *, employee_uuid: str) -> dict:
        rows = await self._db.fetch(
            """
            SELECT event_type, event_date, designation, grade, insight_text
            FROM career_event
            WHERE employee_user_id = (
              SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1
            )
            ORDER BY event_date ASC
            """,
            employee_uuid,
        )

        milestones = [
            {
                "event_type": r["event_type"],
                "event_date": r["event_date"].isoformat() if r["event_date"] else None,
                "designation": r["designation"],
                "grade": r["grade"],
            }
            for r in rows
        ]

        narrative = await self._generate_narrative(rows)
        return {"insights": {"narrative": narrative, "milestones": milestones}}

    async def _generate_narrative(self, rows: list) -> str:
        if not rows:
            return "Your career journey in PRANA is just getting started — insights will appear as documents are added."

        events_summary = [
            {
                "event_type": r["event_type"],
                "designation": r["designation"],
                "grade": r["grade"],
                "note": r["insight_text"],
            }
            for r in rows
        ]
        user_msg = (
            f"Career event history (chronological): {json.dumps(events_summary, ensure_ascii=False)}\n\n"
            "Generate a brief narrative of this career journey."
        )
        try:
            return await self._llm.complete(
                system=_NARRATIVE_SYSTEM,
                user=user_msg,
                max_tokens=250,
                temperature=0.3,
            )
        except Exception as exc:
            log.warning("LLM career narrative generation failed: %s", exc)
            return _fallback_narrative(rows)


def _fallback_narrative(rows: list) -> str:
    designations = [r["designation"] for r in rows if r["designation"]]
    if not designations:
        return "Your career history is being built as more documents are added to your vault."
    if len(designations) == 1:
        return f"Your career journey began as {designations[0]}."
    return f"Your career has progressed from {designations[0]} to {designations[-1]}."
