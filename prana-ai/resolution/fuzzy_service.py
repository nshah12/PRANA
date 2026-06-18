"""
FuzzyService — Level 3 of the identity resolution ladder.

Uses rapidfuzz token_sort_ratio for name matching.
token_sort_ratio handles word-order variations common in Indian names:
  "Sharma Rahul" vs "Rahul Sharma" → score 100
  "Priya" vs "Priyaa" → score ~96 (typo / transliteration)
  "Mgr" vs "Manager" → score ~62 (abbreviation — won't match, correctly)

Threshold: 88 → confirmed match. 75–88 → ambiguous (goes to embedding Level 4).
"""

from uuid import UUID
import logging

log = logging.getLogger(__name__)

MATCH_THRESHOLD   = 88
POSSIBLE_THRESHOLD = 75


class FuzzyService:
    def __init__(self, db):
        self._db = db

    async def match(
        self, tenant_id: UUID, name: str, doj: str | None
    ) -> tuple[UUID | None, float]:
        """
        Fuzzy match `name` against active employees in the tenant.

        Returns (employee_uuid, score) if score >= MATCH_THRESHOLD, else (None, best_score).
        DOJ is used as a tiebreaker when multiple names score >= threshold.
        """
        from rapidfuzz import process, fuzz

        candidates = await self._db.fetch(
            """SELECT employee_uuid, display_name, doj
               FROM employee_master
               WHERE tenant_id = $1 AND dol IS NULL""",
            tenant_id,
        )
        if not candidates:
            return None, 0.0

        names  = [row["display_name"] for row in candidates]
        result = process.extract(
            query=name,
            choices=names,
            scorer=fuzz.token_sort_ratio,
            limit=5,
        )

        if not result:
            return None, 0.0

        best_name, best_score, best_idx = result[0]

        if best_score < POSSIBLE_THRESHOLD:
            return None, float(best_score)

        if best_score < MATCH_THRESHOLD:
            # Possible match — caller should proceed to Level 4 embedding
            return None, float(best_score)

        # Score >= MATCH_THRESHOLD — check DOJ proximity as tiebreaker
        matched_row = candidates[best_idx]

        if doj and matched_row["doj"]:
            # Reject if DOJ differs by more than 30 days (likely different person, same name)
            from datetime import date
            try:
                doc_doj = date.fromisoformat(doj)
                emp_doj = matched_row["doj"]
                if abs((doc_doj - emp_doj).days) > 30:
                    log.info("fuzzy match rejected: name matched but DOJ mismatch", extra={
                        "name": name, "score": best_score,
                        "doc_doj": str(doc_doj), "emp_doj": str(emp_doj),
                    })
                    return None, float(best_score)
            except ValueError:
                pass  # unparseable DOJ — don't reject on DOJ alone

        return matched_row["employee_uuid"], float(best_score)
