"""
Gamification router — career score, badges, check-in streak.

Employee-only endpoints. employee_user_id always from JWT — never from request body or query params.
Privacy contract: no raw salary, CTC, or PAN in any response.
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from dependencies import DbConn, Employee
from services.gamification_service import GamificationService

log = logging.getLogger(__name__)
router = APIRouter()

_svc = GamificationService()


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(db: DbConn, current: Employee):
    """
    Returns career score + breakdown, earned badges, and current streak.
    Score is computed from vault completeness, doc freshness, diversity, engagement.
    No raw salary or PAN in any field.
    """
    emp_id: UUID = UUID(current.user_id)

    # Score (from career_score table, pre-computed by workflow)
    score_row = await db.fetchrow(
        """
        SELECT score, completeness_pts, freshness_pts, diversity_pts,
               engagement_pts, last_calculated_at
        FROM career_score
        WHERE employee_user_id = $1
        """,
        emp_id,
    )

    if score_row:
        score = int(score_row["score"])
        breakdown = {
            "completeness_pts": int(score_row["completeness_pts"]),
            "freshness_pts":    int(score_row["freshness_pts"]),
            "diversity_pts":    int(score_row["diversity_pts"]),
            "engagement_pts":   int(score_row["engagement_pts"]),
        }
    else:
        score = 0
        breakdown = {
            "completeness_pts": 0,
            "freshness_pts":    0,
            "diversity_pts":    0,
            "engagement_pts":   0,
        }

    # Earned badges
    badge_rows = await db.fetch(
        """
        SELECT bd.badge_key, bd.badge_name, bd.badge_icon, bd.category,
               eb.earned_at, eb.context
        FROM employee_badge eb
        JOIN badge_definition bd ON bd.badge_definition_id = eb.badge_definition_id
        WHERE eb.employee_user_id = $1
        ORDER BY eb.earned_at DESC
        """,
        emp_id,
    )
    badges = [
        {
            "badge_key":  r["badge_key"],
            "badge_name": r["badge_name"],
            "badge_icon": r["badge_icon"],
            "category":   r["category"],
            "earned_at":  r["earned_at"].isoformat() if hasattr(r["earned_at"], "isoformat") else (r["earned_at"] or None),
        }
        for r in badge_rows
    ]

    # Streak
    streak_val = await db.fetchval(
        "SELECT current_streak_days FROM employee_streak WHERE employee_user_id = $1",
        emp_id,
    ) or 0
    longest_val = await db.fetchval(
        "SELECT longest_streak_days FROM employee_streak WHERE employee_user_id = $1",
        emp_id,
    ) or 0

    return {
        "score":           score,
        "score_breakdown": breakdown,
        "badges":          badges,
        "streak": {
            "current_streak_days": int(streak_val),
            "longest_streak_days": int(longest_val),
        },
    }


# ── Check-in ──────────────────────────────────────────────────────────────────

@router.post("/checkin")
async def checkin(db: DbConn, current: Employee):
    """
    Record a daily check-in and return updated streak.
    Idempotent — multiple calls on the same day return the same streak.
    Fires gamification recalculation via Kafka → WorkflowConsumer.
    """
    emp_id: UUID = UUID(current.user_id)

    streak_data = await _svc.update_streak(emp_id, db)
    await _svc.persist_streak(emp_id, streak_data, db)

    return {
        "current_streak_days": streak_data["current_streak_days"],
        "longest_streak_days": streak_data["longest_streak_days"],
        "last_checkin_date":   streak_data["last_checkin_date"].isoformat()
            if hasattr(streak_data["last_checkin_date"], "isoformat")
            else str(streak_data["last_checkin_date"]),
    }


# ── Badges ────────────────────────────────────────────────────────────────────

@router.get("/badges")
async def list_badges(db: DbConn, current: Employee):
    """List all badges earned by this employee, newest first."""
    emp_id: UUID = UUID(current.user_id)

    rows = await db.fetch(
        """
        SELECT bd.badge_key, bd.badge_name, bd.badge_icon, bd.category,
               bd.badge_description, eb.earned_at, eb.context_key
        FROM employee_badge eb
        JOIN badge_definition bd ON bd.badge_definition_id = eb.badge_definition_id
        WHERE eb.employee_user_id = $1
        ORDER BY eb.earned_at DESC
        """,
        emp_id,
    )

    badges = [
        {
            "badge_key":         r["badge_key"],
            "badge_name":        r["badge_name"],
            "badge_icon":        r["badge_icon"],
            "category":          r["category"],
            "badge_description": r["badge_description"],
            "earned_at":         r["earned_at"].isoformat() if hasattr(r["earned_at"], "isoformat") else (r["earned_at"] or None),
            "context_key":       r["context_key"],
        }
        for r in rows
    ]

    return {"badges": badges, "total": len(badges)}


# ── Badge catalog (all available badges) ─────────────────────────────────────

@router.get("/catalog")
async def badge_catalog(db: DbConn, current: Employee):
    """Return all badge definitions so the mobile app can show locked/unlocked states."""
    emp_id: UUID = UUID(current.user_id)

    all_defs = await db.fetch(
        """
        SELECT badge_key, badge_name, badge_icon, badge_description, category, sort_order
        FROM badge_definition
        WHERE is_active = TRUE
        ORDER BY sort_order
        """
    )

    earned_keys = {
        r["badge_key"] async for r in _aiter(
            await db.fetch(
                """
                SELECT bd.badge_key
                FROM employee_badge eb
                JOIN badge_definition bd ON bd.badge_definition_id = eb.badge_definition_id
                WHERE eb.employee_user_id = $1
                """,
                emp_id,
            )
        )
    }

    return {
        "catalog": [
            {
                "badge_key":         r["badge_key"],
                "badge_name":        r["badge_name"],
                "badge_icon":        r["badge_icon"],
                "badge_description": r["badge_description"],
                "category":          r["category"],
                "earned":            r["badge_key"] in earned_keys,
            }
            for r in all_defs
        ]
    }


async def _aiter(rows):
    for r in rows:
        yield r


# ── Coaching actions ───────────────────────────────────────────────────────────

@router.get("/coaching")
async def get_coaching_actions(db: DbConn, current: Employee):
    """
    Returns up to 10 personalised actions the employee can take to raise
    their career score, ordered by priority then score_impact descending.

    Each action carries:
      score_impact  — estimated pts gain if completed
      pillar        — which score pillar it improves
      cta           — REQUEST | UPLOAD | CHECKIN
      cta_route     — deep-link into the mobile app

    Privacy: no raw salary, CTC, or PAN in any field.
    """
    emp_id: UUID = UUID(current.user_id)
    actions = await _svc.get_coaching_actions(emp_id, db)
    return {"coaching": actions, "total": len(actions)}
