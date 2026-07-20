"""
GamificationRefreshWorkflow — thin Temporal adapter.

Triggered by WorkflowConsumer on DOC_ROUTED event.
Delegates all logic to GamificationService (zero Temporal imports there).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio import activity

from services.gamification_service import GamificationService


@dataclass
class GamificationRefreshInput:
    employee_user_id: str


# ── Activities ────────────────────────────────────────────────────────────────

@activity.defn
async def recalculate_and_persist(employee_user_id: str) -> dict:
    """Recalculate score + badges + streak and persist all to DB."""
    import asyncpg
    import os
    uid = UUID(employee_user_id)
    svc = GamificationService()

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        score_data  = await svc.recalculate_score(uid, conn)
        badge_keys  = await svc.check_and_award_badges(uid, conn)
        await svc.persist_score(uid, score_data, conn)
        if badge_keys:
            await svc.persist_badges(uid, badge_keys, conn)
    finally:
        await conn.close()

    return {"score": score_data["score"], "new_badges": badge_keys}


# ── Workflow shell (<20 lines) ────────────────────────────────────────────────

@workflow.defn
class GamificationRefreshWorkflow:
    @workflow.run
    async def run(self, inp: GamificationRefreshInput) -> dict:
        return await workflow.execute_activity(
            recalculate_and_persist,
            inp.employee_user_id,
            start_to_close_timeout=timedelta(minutes=2),
        )
