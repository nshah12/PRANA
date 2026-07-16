"""
SeverityPolicyService — the single, PA-editable source of truth for incident
severity (P0-P3) and SLA policy, replacing hardcoded constants formerly
scattered across services/incident_service.py, services/error_threshold_service.py,
services/health_service.py, and workflows/activities.py + kafka consumers.

See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md for the full design and
prana-db/migrations/041_severity_sla_policy.sql for the seeded rule set.

Evaluation algorithm (resolve_severity):
  Rules for a domain are tried in ascending priority order.
    - DEFAULT rules are a wildcard: they match any value.
    - PREFIX/EXACT rules only match if the value matches their pattern.
  If a rule matches but its occurrence_threshold/occurrence_threshold_max/window_minutes
  condition is NOT satisfied:
    - a PREFIX/EXACT rule is terminal — evaluation stops, no severity is returned.
      (A specific rule "claims" this value; if its own promotion condition isn't
      met, that's a decision, not an invitation to try other rules.)
    - a DEFAULT rule falls through to the next rule instead, so a tiered wildcard
      cascade (e.g. "first occurrence" then "noisy recurrence") can compose.
"""
import uuid
from typing import Any, Optional


class SeverityPolicyService:

    def __init__(self, db) -> None:
        self._db = db

    async def resolve_severity(
        self,
        *,
        domain: str,
        value: str,
        occurrence_count: int = 1,
        span_minutes: Optional[float] = None,
    ) -> Optional[str]:
        rows = await self._db.fetch(
            "SELECT match_type, match_value, occurrence_threshold, occurrence_threshold_max, "
            "window_minutes, severity FROM severity_classification_rule "
            "WHERE domain = $1 AND is_active = TRUE ORDER BY priority ASC",
            domain,
        )

        for row in rows:
            is_wildcard = row["match_type"] == "DEFAULT"
            if is_wildcard:
                matched = True
            elif row["match_type"] == "PREFIX":
                matched = value.startswith(row["match_value"] or "\0")
            elif row["match_type"] == "EXACT":
                matched = value == row["match_value"]
            else:
                matched = False

            if not matched:
                continue

            if self._threshold_satisfied(row, occurrence_count, span_minutes):
                return row["severity"]
            if not is_wildcard:
                return None

        return None

    @staticmethod
    def _threshold_satisfied(row: dict, occurrence_count: int, span_minutes: Optional[float]) -> bool:
        if row["occurrence_threshold"] is not None and occurrence_count < row["occurrence_threshold"]:
            return False
        if row["occurrence_threshold_max"] is not None and occurrence_count > row["occurrence_threshold_max"]:
            return False
        if row["window_minutes"] is not None and span_minutes is not None and span_minutes > row["window_minutes"]:
            return False
        return True

    async def get_rule_threshold(self, *, domain: str, match_value: str) -> Optional[dict[str, Any]]:
        """Read a single EXACT rule's own occurrence_threshold/window_minutes — used by the
        anomaly-detection engine (workflows/security.py) to know what count-in-window counts
        as 'bulk' BEFORE it has an occurrence_count to classify. The same row's severity is
        applied afterwards via resolve_severity(), so there's one number to edit, not two."""
        row = await self._db.fetchrow(
            "SELECT occurrence_threshold, window_minutes FROM severity_classification_rule "
            "WHERE domain = $1 AND match_type = 'EXACT' AND match_value = $2 AND is_active = TRUE "
            "ORDER BY priority ASC LIMIT 1",
            domain, match_value,
        )
        if not row:
            return None
        return {"occurrence_threshold": row["occurrence_threshold"], "window_minutes": row["window_minutes"]}

    async def get_sla(self, *, severity: str) -> Optional[dict[str, Any]]:
        row = await self._db.fetchrow(
            "SELECT sla_minutes, auto_create_incident FROM sla_policy WHERE severity = $1",
            severity,
        )
        if not row:
            return None
        return {"sla_minutes": row["sla_minutes"], "auto_create_incident": row["auto_create_incident"]}

    async def get_all_sla_policies(self) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            "SELECT severity, sla_minutes, auto_create_incident, description, updated_by, updated_at "
            "FROM sla_policy ORDER BY severity"
        )
        return [self._sla_row(r) for r in rows]

    async def update_sla_policy(
        self, *, severity: str, sla_minutes: Optional[int], auto_create_incident: Optional[bool],
        description: Optional[str], updated_by: str,
    ) -> dict[str, Any]:
        """PA-facing edit (prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §5). Fields left as
        None are left unchanged (COALESCE) — callers only pass fields the PA actually
        submitted, so an omitted field can't be silently zeroed out."""
        exists = await self._db.fetchval("SELECT 1 FROM sla_policy WHERE severity=$1", severity)
        if not exists:
            raise ValueError(f"No SLA policy for severity {severity}")

        await self._db.execute(
            """
            UPDATE sla_policy
               SET sla_minutes = COALESCE($2, sla_minutes),
                   auto_create_incident = COALESCE($3, auto_create_incident),
                   description = COALESCE($4, description),
                   updated_by = $5, updated_at = NOW()
             WHERE severity = $1
            """,
            severity, sla_minutes, auto_create_incident, description, updated_by,
        )
        row = await self._db.fetchrow(
            "SELECT severity, sla_minutes, auto_create_incident, description, updated_by, updated_at "
            "FROM sla_policy WHERE severity=$1",
            severity,
        )
        return self._sla_row(row)

    @staticmethod
    def _sla_row(r) -> dict[str, Any]:
        return {
            "severity": r["severity"],
            "sla_minutes": r["sla_minutes"],
            "auto_create_incident": r["auto_create_incident"],
            "description": r["description"],
            "updated_by": str(r["updated_by"]) if r["updated_by"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }

    # ── severity_classification_rule CRUD (PA-facing) ────────────────────────

    async def list_severity_rules(self, *, domain: Optional[str] = None) -> list[dict[str, Any]]:
        if domain:
            rows = await self._db.fetch(
                """
                SELECT rule_id, domain, match_type, match_value, occurrence_threshold,
                       occurrence_threshold_max, window_minutes, severity, priority, is_active,
                       description, updated_by, updated_at
                FROM severity_classification_rule
                WHERE domain=$1 ORDER BY domain, priority
                """,
                domain,
            )
        else:
            rows = await self._db.fetch(
                """
                SELECT rule_id, domain, match_type, match_value, occurrence_threshold,
                       occurrence_threshold_max, window_minutes, severity, priority, is_active,
                       description, updated_by, updated_at
                FROM severity_classification_rule
                ORDER BY domain, priority
                """
            )
        return [self._rule_row(r) for r in rows]

    async def create_severity_rule(
        self, *, domain: str, match_type: str, match_value: Optional[str],
        occurrence_threshold: Optional[int], occurrence_threshold_max: Optional[int],
        window_minutes: Optional[int], severity: str, priority: int,
        description: Optional[str], updated_by: str,
    ) -> dict[str, Any]:
        if match_type not in ("PREFIX", "EXACT", "DEFAULT"):
            raise ValueError("match_type must be PREFIX, EXACT, or DEFAULT")
        if match_type != "DEFAULT" and not match_value:
            raise ValueError("match_value is required unless match_type is DEFAULT")

        rule_id = uuid.uuid4()
        await self._db.execute(
            """
            INSERT INTO severity_classification_rule
              (rule_id, domain, match_type, match_value, occurrence_threshold,
               occurrence_threshold_max, window_minutes, severity, priority,
               description, updated_by, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW())
            """,
            rule_id, domain, match_type, match_value, occurrence_threshold,
            occurrence_threshold_max, window_minutes, severity, priority,
            description, updated_by,
        )
        row = await self._db.fetchrow(
            """
            SELECT rule_id, domain, match_type, match_value, occurrence_threshold,
                   occurrence_threshold_max, window_minutes, severity, priority, is_active,
                   description, updated_by, updated_at
            FROM severity_classification_rule WHERE rule_id=$1
            """,
            rule_id,
        )
        return self._rule_row(row)

    async def update_severity_rule(
        self, *, rule_id: str, occurrence_threshold: Optional[int] = None,
        occurrence_threshold_max: Optional[int] = None, window_minutes: Optional[int] = None,
        severity: Optional[str] = None, priority: Optional[int] = None,
        is_active: Optional[bool] = None, description: Optional[str] = None,
        updated_by: str,
    ) -> dict[str, Any]:
        exists = await self._db.fetchval(
            "SELECT 1 FROM severity_classification_rule WHERE rule_id=$1", rule_id,
        )
        if not exists:
            raise ValueError(f"Rule {rule_id} not found")

        await self._db.execute(
            """
            UPDATE severity_classification_rule
               SET occurrence_threshold = COALESCE($2, occurrence_threshold),
                   occurrence_threshold_max = COALESCE($3, occurrence_threshold_max),
                   window_minutes = COALESCE($4, window_minutes),
                   severity = COALESCE($5, severity),
                   priority = COALESCE($6, priority),
                   is_active = COALESCE($7, is_active),
                   description = COALESCE($8, description),
                   updated_by = $9, updated_at = NOW()
             WHERE rule_id = $1
            """,
            rule_id, occurrence_threshold, occurrence_threshold_max, window_minutes,
            severity, priority, is_active, description, updated_by,
        )
        row = await self._db.fetchrow(
            """
            SELECT rule_id, domain, match_type, match_value, occurrence_threshold,
                   occurrence_threshold_max, window_minutes, severity, priority, is_active,
                   description, updated_by, updated_at
            FROM severity_classification_rule WHERE rule_id=$1
            """,
            rule_id,
        )
        return self._rule_row(row)

    @staticmethod
    def _rule_row(r) -> dict[str, Any]:
        return {
            "rule_id": str(r["rule_id"]),
            "domain": r["domain"],
            "match_type": r["match_type"],
            "match_value": r["match_value"],
            "occurrence_threshold": r["occurrence_threshold"],
            "occurrence_threshold_max": r["occurrence_threshold_max"],
            "window_minutes": r["window_minutes"],
            "severity": r["severity"],
            "priority": r["priority"],
            "is_active": r["is_active"],
            "description": r["description"],
            "updated_by": str(r["updated_by"]) if r["updated_by"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
