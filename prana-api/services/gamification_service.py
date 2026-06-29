"""
GamificationService — career score, badge engine, check-in streak.

Privacy contract: no raw salary, CTC, or PAN in any output.
Score is computed from doc counts, freshness, and engagement — never financial values.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

log = logging.getLogger(__name__)

# ── Score weights ─────────────────────────────────────────────────────────────
_COMPLETENESS_MAX = 40   # pts from vault coverage
_FRESHNESS_MAX    = 30   # pts from how recently docs arrived
_DIVERSITY_MAX    = 20   # pts from unique doc types (2 pts each, cap 10 types)
_ENGAGEMENT_MAX   = 10   # pts from streak days (1 pt each, cap 10)

# Freshness bands (days since most recent routed doc)
_FRESH_FULL  = 30    # 30 pts
_FRESH_MED   = 90    # 20 pts
_FRESH_LOW   = 180   # 10 pts
                     # > 180 days → 0 pts

# Badge keys that can be earned only once (no context key)
_ONCE_BADGES = {
    "VAULT_STARTER", "TAX_READY", "CAREER_CHRONICLER",
    "MULTI_ORG", "CAREER_DECADE",
    "STREAK_3", "STREAK_7", "STREAK_30", "ASK_CURIOUS",
}

# Badge keys that repeat per fiscal year
_PER_YEAR_BADGES = {"FULL_YEAR"}


class GamificationService:

    # ── Score ─────────────────────────────────────────────────────────────────

    async def recalculate_score(self, employee_user_id: UUID, db) -> dict:
        """
        Compute 0–100 career score for an employee.

        Returns dict with score + 4 component breakdowns.
        Does NOT write to DB — caller (workflow) persists the result.
        """
        # 1. Fetch routed documents (not deleted)
        doc_rows = await db.fetch(
            """
            SELECT d.doc_type, d.routed_at
            FROM document d
            JOIN employee_master em ON em.employee_uuid = d.employee_uuid
            WHERE em.employee_user_id = $1
              AND d.pipeline_status = 'ROUTED'
              AND d.is_deleted = FALSE
            """,
            employee_user_id,
        )

        # 2. Fetch employer tenure rows for diversity/completeness
        master_rows = await db.fetch(
            """
            SELECT tenant_id, doj, dol, vault_completeness
            FROM employee_master
            WHERE employee_user_id = $1
            ORDER BY doj ASC
            """,
            employee_user_id,
        )

        # 3. Current streak days from employee_streak
        streak_days = await db.fetchval(
            "SELECT current_streak_days FROM employee_streak WHERE employee_user_id = $1",
            employee_user_id,
        ) or 0

        completeness_pts = self._completeness_pts(master_rows)
        freshness_pts    = self._freshness_pts(doc_rows)
        diversity_pts    = self._diversity_pts(doc_rows)
        engagement_pts   = min(int(streak_days), _ENGAGEMENT_MAX)

        score = min(
            completeness_pts + freshness_pts + diversity_pts + engagement_pts,
            100,
        )

        return {
            "score":            score,
            "completeness_pts": completeness_pts,
            "freshness_pts":    freshness_pts,
            "diversity_pts":    diversity_pts,
            "engagement_pts":   engagement_pts,
        }

    def _completeness_pts(self, master_rows) -> int:
        if not master_rows:
            return 0
        avg = sum(float(r["vault_completeness"] or 0) for r in master_rows) / len(master_rows)
        # vault_completeness is 0–100 pct; map to 0–40 pts
        return min(int(avg * _COMPLETENESS_MAX / 100), _COMPLETENESS_MAX)

    def _freshness_pts(self, doc_rows) -> int:
        if not doc_rows:
            return 0
        routed_dates = [r["routed_at"] for r in doc_rows if r["routed_at"]]
        if not routed_dates:
            return 0
        most_recent = max(routed_dates)
        # routed_at may be a date or datetime — normalise to date
        if hasattr(most_recent, "date"):
            most_recent = most_recent.date()
        days_ago = (date.today() - most_recent).days
        if days_ago <= _FRESH_FULL:
            return 30
        if days_ago <= _FRESH_MED:
            return 20
        if days_ago <= _FRESH_LOW:
            return 10
        return 0

    def _diversity_pts(self, doc_rows) -> int:
        unique_types = len({r["doc_type"] for r in doc_rows})
        return min(unique_types * 2, _DIVERSITY_MAX)

    # ── Badge engine ──────────────────────────────────────────────────────────

    async def check_and_award_badges(
        self, employee_user_id: UUID, db
    ) -> list[str]:
        """
        Evaluate badge conditions and return list of newly-awarded badge keys.

        Does NOT write to DB — caller persists the awards.
        """
        # Reload docs and masters for badge evaluation
        doc_rows = await db.fetch(
            """
            SELECT d.doc_type, d.routed_at, d.doc_period
            FROM document d
            JOIN employee_master em ON em.employee_uuid = d.employee_uuid
            WHERE em.employee_user_id = $1
              AND d.pipeline_status = 'ROUTED'
              AND d.is_deleted = FALSE
            """,
            employee_user_id,
        )
        master_rows = await db.fetch(
            "SELECT tenant_id, doj, dol FROM employee_master WHERE employee_user_id = $1",
            employee_user_id,
        )
        streak_days = await db.fetchval(
            "SELECT current_streak_days FROM employee_streak WHERE employee_user_id = $1",
            employee_user_id,
        ) or 0

        # All badge definitions
        badge_defs = await db.fetch(
            "SELECT badge_definition_id, badge_key, category FROM badge_definition WHERE is_active = TRUE"
        )

        # Already-earned (badge_key + context_key pairs)
        already_earned = await db.fetch(
            """
            SELECT bd.badge_key, eb.context_key
            FROM employee_badge eb
            JOIN badge_definition bd ON bd.badge_definition_id = eb.badge_definition_id
            WHERE eb.employee_user_id = $1
            """,
            employee_user_id,
        )
        earned_set = {(r["badge_key"], r["context_key"]) for r in already_earned}

        doc_types  = {r["doc_type"] for r in doc_rows}
        n_docs     = len(doc_rows)
        tenant_ids = {str(r["tenant_id"]) for r in master_rows}

        newly_awarded: list[str] = []

        for bd in badge_defs:
            key = bd["badge_key"]
            if not self._badge_condition_met(
                key, doc_types, n_docs, tenant_ids, master_rows, streak_days
            ):
                continue

            context_key = self._context_key(key, doc_rows)
            if (key, context_key) in earned_set:
                continue

            newly_awarded.append(key)

        return newly_awarded

    def _badge_condition_met(
        self, key, doc_types, n_docs, tenant_ids, master_rows, streak_days
    ) -> bool:
        if key == "VAULT_STARTER":
            return n_docs >= 1
        if key == "TAX_READY":
            return "FORM_16" in doc_types
        if key == "FULL_YEAR":
            return self._has_full_year_slips(doc_types)  # simplified: checked in caller
        if key == "CAREER_CHRONICLER":
            return len(doc_types) >= 5
        if key == "MULTI_ORG":
            return len(tenant_ids) >= 3
        if key == "CAREER_DECADE":
            return self._career_years(master_rows) >= 10
        if key == "STREAK_3":
            return streak_days >= 3
        if key == "STREAK_7":
            return streak_days >= 7
        if key == "STREAK_30":
            return streak_days >= 30
        if key == "ASK_CURIOUS":
            return False   # tracked by ask_service, not doc pipeline
        return False

    def _has_full_year_slips(self, doc_types) -> bool:
        return "SALARY_SLIP" in doc_types

    def _career_years(self, master_rows) -> int:
        if not master_rows:
            return 0
        earliest = min(r["doj"] for r in master_rows)
        latest_end = max(
            r["dol"] if r["dol"] else date.today()
            for r in master_rows
        )
        return (latest_end - earliest).days // 365

    def _context_key(self, badge_key: str, doc_rows) -> str:
        if badge_key == "FULL_YEAR":
            # Context key = fiscal year string, e.g. "2024-25"
            # Derive from most recent salary slip doc_period
            periods = [
                r["doc_period"] for r in doc_rows
                if r["doc_type"] == "SALARY_SLIP" and r["doc_period"]
            ]
            if periods:
                # doc_period like "2024-03" → fiscal year "2023-24"
                latest = max(periods)
                year = int(latest.split("-")[0])
                month = int(latest.split("-")[1])
                fy_start = year if month >= 4 else year - 1
                return f"{fy_start}-{str(fy_start + 1)[-2:]}"
        return ""

    # ── Streak ────────────────────────────────────────────────────────────────

    async def update_streak(self, employee_user_id: UUID, db) -> dict:
        """
        Record a check-in and return updated streak info.

        Does NOT write to DB — caller persists.
        """
        today = date.today()
        row = await db.fetchrow(
            "SELECT current_streak_days, longest_streak_days, last_checkin_date, "
            "streak_started_date, total_checkins FROM employee_streak WHERE employee_user_id = $1",
            employee_user_id,
        )

        if row is None:
            return {
                "current_streak_days": 1,
                "longest_streak_days": 1,
                "last_checkin_date":   today,
                "streak_started_date": today,
                "total_checkins":      1,
                "is_new": True,
            }

        last = row["last_checkin_date"]
        current = row["current_streak_days"]
        longest = row["longest_streak_days"]
        total   = row["total_checkins"]

        if last == today:
            # Already checked in today — no change
            return {
                "current_streak_days": current,
                "longest_streak_days": longest,
                "last_checkin_date":   last,
                "streak_started_date": row["streak_started_date"],
                "total_checkins":      total,
                "is_new": False,
            }

        if last == today - timedelta(days=1):
            # Consecutive day
            current += 1
        else:
            # Streak broken
            current = 1

        longest = max(longest, current)
        total   += 1
        streak_started = today - timedelta(days=current - 1)

        return {
            "current_streak_days": current,
            "longest_streak_days": longest,
            "last_checkin_date":   today,
            "streak_started_date": streak_started,
            "total_checkins":      total,
            "is_new": False,
        }

    # ── Persist helpers (called by workflow, not HTTP handler) ────────────────

    async def persist_score(self, employee_user_id: UUID, score_data: dict, db) -> None:
        await db.execute(
            """
            INSERT INTO career_score
                (employee_user_id, score, completeness_pts, freshness_pts,
                 diversity_pts, engagement_pts, last_calculated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (employee_user_id) DO UPDATE SET
                score             = EXCLUDED.score,
                completeness_pts  = EXCLUDED.completeness_pts,
                freshness_pts     = EXCLUDED.freshness_pts,
                diversity_pts     = EXCLUDED.diversity_pts,
                engagement_pts    = EXCLUDED.engagement_pts,
                last_calculated_at = NOW()
            """,
            employee_user_id,
            score_data["score"],
            score_data["completeness_pts"],
            score_data["freshness_pts"],
            score_data["diversity_pts"],
            score_data["engagement_pts"],
        )

    async def persist_badges(
        self, employee_user_id: UUID, badge_keys: list[str], db
    ) -> None:
        for key in badge_keys:
            row = await db.fetchrow(
                "SELECT badge_definition_id FROM badge_definition WHERE badge_key = $1", key
            )
            if not row:
                continue
            context_key = ""   # FULL_YEAR context handled separately if needed
            await db.execute(
                """
                INSERT INTO employee_badge
                    (employee_user_id, badge_definition_id, context_key, earned_at, context)
                VALUES ($1, $2, $3, NOW(), '{}')
                ON CONFLICT (employee_user_id, badge_definition_id, context_key) DO NOTHING
                """,
                employee_user_id, row["badge_definition_id"], context_key,
            )

    async def persist_streak(
        self, employee_user_id: UUID, streak_data: dict, db
    ) -> None:
        if streak_data.get("is_new"):
            await db.execute(
                """
                INSERT INTO employee_streak
                    (employee_user_id, current_streak_days, longest_streak_days,
                     last_checkin_date, streak_started_date, total_checkins, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                """,
                employee_user_id,
                streak_data["current_streak_days"],
                streak_data["longest_streak_days"],
                streak_data["last_checkin_date"],
                streak_data["streak_started_date"],
                streak_data["total_checkins"],
            )
        else:
            await db.execute(
                """
                UPDATE employee_streak SET
                    current_streak_days = $2,
                    longest_streak_days = $3,
                    last_checkin_date   = $4,
                    streak_started_date = $5,
                    total_checkins      = $6,
                    updated_at          = NOW()
                WHERE employee_user_id = $1
                """,
                employee_user_id,
                streak_data["current_streak_days"],
                streak_data["longest_streak_days"],
                streak_data["last_checkin_date"],
                streak_data["streak_started_date"],
                streak_data["total_checkins"],
            )
