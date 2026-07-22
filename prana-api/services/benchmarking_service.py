"""
BenchmarkingService — comp intelligence for employees and CHROs.

k-anonymity rule: cohort must have >= K_MIN employees before any stat is published.
Below K_MIN → suppressed=True, label_text = "Not enough data yet".

Privacy rules:
- No raw ₹ salary ever stored or returned — only percentile bands and labels.
- CHRO sees their org's own grade bands vs. market median (no individual data).
- Employee sees their own percentile within their cohort — no peers' individual data.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

K_MIN = 50  # minimum cohort size before any stat is published


def _cohort_key(designation: str, industry: str, city: str, experience_band: str) -> str:
    """Deterministic cohort identifier — lowercase, hyphenated, pipe-separated."""
    def slug(s: str) -> str:
        return s.lower().strip().replace(' ', '-')
    return f"{slug(designation)}|{slug(industry)}|{slug(city)}|{slug(experience_band)}"


def _experience_band(years: float) -> str:
    if years < 2:   return "0-2y"
    if years < 5:   return "2-5y"
    if years < 8:   return "5-8y"
    if years < 12:  return "8-12y"
    return "12y+"


class BenchmarkingService:
    def __init__(self, db, config: dict | None = None):
        self._db     = db
        self._config = config or {}

    # ── Employee-facing ──────────────────────────────────────────────────────

    async def set_benchmark_consent(
        self,
        employee_user_id: str,
        grant: bool,
    ) -> dict[str, Any]:
        """
        Employee grants or withdraws peer_benchmark consent.
        On withdrawal: marks all their comp_contribution rows as withdrawn.
        """
        async with self._db.transaction():
            await self._db.execute(
                """
                INSERT INTO employee_consent
                  (employee_user_id, purpose, is_active, consent_version, updated_at)
                VALUES ($1, 'peer_benchmark', $2, '1.0', NOW())
                ON CONFLICT (employee_user_id, purpose)
                DO UPDATE SET is_active = EXCLUDED.is_active, updated_at = NOW()
                """,
                employee_user_id, grant,
            )
            if not grant:
                await self._db.execute(
                    """
                    UPDATE comp_contribution
                    SET    withdrawn_at = NOW()
                    WHERE  employee_user_id = $1 AND withdrawn_at IS NULL
                    """,
                    employee_user_id,
                )
        return {"peer_benchmark_consent": grant}

    async def get_benchmark_consent(self, employee_user_id: str) -> dict[str, Any]:
        row = await self._db.fetchrow(
            """
            SELECT is_active, updated_at FROM employee_consent
            WHERE employee_user_id = $1 AND purpose = 'peer_benchmark'
            """,
            employee_user_id,
        )
        return {
            "peer_benchmark_consent": bool(row["is_active"]) if row else False,
            "updated_at": row["updated_at"].isoformat() if row and row["updated_at"] else None,
        }

    async def get_employee_benchmark(self, employee_user_id: str) -> dict[str, Any]:
        """
        Returns all cohort results for this employee.
        Suppressed results show progress toward K_MIN (encourages patience, not confusion).
        """
        rows = await self._db.fetch(
            """
            SELECT cohort_key, percentile_band, cohort_size, suppressed, label_text, computed_at
            FROM   peer_benchmark_result
            WHERE  employee_user_id = $1
            ORDER  BY computed_at DESC
            LIMIT  10
            """,
            employee_user_id,
        )
        return {
            "items": [_serialize_result_for_employee(r) for r in rows],
            "k_min": K_MIN,
        }

    # ── CHRO / analytics facing ───────────────────────────────────────────────

    async def get_chro_unopted_count(self, tenant_id: str) -> dict[str, Any]:
        """
        How many active employees in this tenant have NOT opted in to peer_benchmark.
        CHRO uses this to understand how many more opt-ins are needed to publish bands.
        """
        total_active = await self._db.fetchval(
            "SELECT COUNT(*) FROM employee_master WHERE tenant_id = $1 AND dol IS NULL AND is_deleted = FALSE",
            tenant_id,
        )
        opted_in = await self._db.fetchval(
            """
            SELECT COUNT(DISTINCT em.employee_user_id)
            FROM   employee_master em
            JOIN   employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.purpose          = 'peer_benchmark'
                  AND ec.tenant_id        IS NULL
                  AND ec.is_active        = TRUE
            WHERE  em.tenant_id = $1 AND em.dol IS NULL AND em.is_deleted = FALSE
            """,
            tenant_id,
        )
        total_active = int(total_active or 0)
        opted_in     = int(opted_in or 0)
        return {
            "total_active_employees": total_active,
            "opted_in":               opted_in,
            "not_opted_in":           total_active - opted_in,
            "opt_in_rate_pct":        round(opted_in / total_active * 100, 1) if total_active else 0,
        }

    async def get_chro_comp_bands(
        self,
        tenant_id: str,
        grade:      str | None = None,
        department: str | None = None,
        period:     str | None = None,
    ) -> dict[str, Any]:
        """
        CHRO sees their org's comp bands vs cross-tenant market median.
        Uses $N IS NULL guard to avoid f-string SQL (DB-01).
        Returns percentile labels — never raw ₹ figures in API response.
        """
        rows = await self._db.fetch(
            """
            SELECT grade, department, period, sample_count, p25, p50, p75,
                   suppressed, computed_at
            FROM   chro_comp_intelligence
            WHERE  tenant_id = $1
              AND  ($2::text IS NULL OR grade      = $2)
              AND  ($3::text IS NULL OR department = $3)
              AND  ($4::text IS NULL OR period     = $4)
            ORDER  BY period DESC, grade ASC
            LIMIT  200
            """,
            tenant_id, grade, department, period,
        )
        return {
            "items":  [_serialize_band_for_chro(r) for r in rows],
            "k_min":  K_MIN,
            "note":   "Bands with fewer than 50 contributors are suppressed for privacy.",
        }

    async def get_market_median(
        self,
        grade:            str,
        department:       str,
        period:           str | None = None,
    ) -> dict[str, Any]:
        """
        Cross-tenant market median for a given grade+department cohort.
        Only published when sample_count >= K_MIN.
        """
        row = await self._db.fetchrow(
            """
            SELECT p25, p50, p75, sample_count, computed_at
            FROM   salary_band
            WHERE  tenant_id  IS NULL
              AND  grade      = $1
              AND  department = $2
              AND  ($3::text IS NULL OR period = $3)
            ORDER  BY computed_at DESC
            LIMIT  1
            """,
            grade, department, period,
        )
        if not row:
            return {"suppressed": True, "reason": "NO_DATA"}
        if (row["sample_count"] or 0) < K_MIN:
            return {"suppressed": True, "reason": "BELOW_K_MIN", "k_min": K_MIN}
        return {
            "suppressed":    False,
            "grade":         grade,
            "department":    department,
            "period":        period,
            "p25_label":     "P25",
            "p50_label":     "Median",
            "p75_label":     "P75",
            # Band labels — not raw ₹ values.
            # The frontend renders these as "P25 / Median / P75" markers on a range bar.
            # Raw paise values from p25/p50/p75 are used only for chart positioning,
            # never displayed as text to CHRO.
            "p25":           row["p25"],
            "p50":           row["p50"],
            "p75":           row["p75"],
            "sample_count":  row["sample_count"],
            "computed_at":   row["computed_at"].isoformat(),
        }


# ── Serializers ──────────────────────────────────────────────────────────────

def _plain_language_label(percentile_band: str, designation: str, city: str) -> str:
    """Converts 'P60-P75' into a sentence a non-data-person understands."""
    band_map = {
        "P0-P25":  ("earn less than 75% of", "Consider discussing your comp at your next review."),
        "P25-P40": ("earn more than 25% of", "You're in the lower-middle range for your peer group."),
        "P40-P60": ("are right in the middle among", "Your comp is in line with the market median."),
        "P60-P75": ("earn more than 60% of", "Your comp is above the market median — well positioned."),
        "P75+":    ("are in the top 25% among", "Your comp is among the highest for your peer group."),
    }
    phrase, context = band_map.get(percentile_band, ("are in the", ""))
    return f"You {phrase} {designation}s in {city}. {context}".strip()

def _days_ago(dt: Any) -> str:
    from datetime import datetime, timezone
    if not dt:
        return "unknown"
    if hasattr(dt, 'date'):
        aware_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - aware_dt).days
    else:
        return "unknown"
    if days == 0: return "today"
    if days == 1: return "yesterday"
    if days < 30: return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"

def _serialize_result_for_employee(r: Any) -> dict[str, Any]:
    """
    Employee sees plain-language explanation + cohort progress toward K_MIN.
    Never raw salary, never cohort_size when suppressed.
    """
    cohort_parts = str(r["cohort_key"]).split("|")
    designation  = cohort_parts[0].replace("-", " ").title() if cohort_parts else ""
    city         = cohort_parts[2].replace("-", " ").title() if len(cohort_parts) > 2 else ""

    if r["suppressed"]:
        contributors = int(r["cohort_size"] or 0)
        needed       = K_MIN - contributors
        label        = (
            f"More data needed: {contributors} of {K_MIN} contributors needed to unlock your benchmark. "
            f"{needed} more peer{'s' if needed != 1 else ''} to go — check back after the next payroll cycle."
        )
        percentile_band = None
        plain_label     = label
    else:
        percentile_band = r["percentile_band"]
        plain_label     = (
            _plain_language_label(percentile_band, designation, city)
            if percentile_band else (r["label_text"] or "")
        )

    return {
        "cohort_key":      str(r["cohort_key"]),
        "designation":     designation,
        "industry":        cohort_parts[1].replace("-", " ").title() if len(cohort_parts) > 1 else "",
        "city":            city,
        "experience_band": cohort_parts[3] if len(cohort_parts) > 3 else "",
        "percentile_band": percentile_band,
        "label_text":      plain_label,
        "suppressed":      bool(r["suppressed"]),
        "cohort_progress": {
            "current": int(r["cohort_size"] or 0),
            "needed":  K_MIN,
        } if r["suppressed"] else None,
        "data_freshness":  _days_ago(r["computed_at"]),
        "computed_at":     r["computed_at"].isoformat() if r["computed_at"] else None,
    }

def _serialize_band_for_chro(r: Any) -> dict[str, Any]:
    """
    CHRO sees bands with raw p25/p50/p75 paise values for chart positioning.
    These are used as chart axis data — never displayed as text labels.
    The frontend must render them as 'P25 / Median / P75' markers, not ₹ amounts.
    """
    return {
        "grade":        r["grade"]      or "",
        "department":   r["department"] or "",
        "period":       r["period"]     or "",
        "sample_count": r["sample_count"],
        "suppressed":   bool(r["suppressed"]),
        # Raw values for chart positioning — frontend MUST NOT render as currency text
        "p25": r["p25"] if not r["suppressed"] else None,
        "p50": r["p50"] if not r["suppressed"] else None,
        "p75": r["p75"] if not r["suppressed"] else None,
        "computed_at":    r["computed_at"].isoformat(),
        "data_freshness": _days_ago(r["computed_at"]),
    }
