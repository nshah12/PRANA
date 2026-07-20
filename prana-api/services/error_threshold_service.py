"""
ErrorThresholdService — implements §5 of prana-docs/ERROR_OBSERVABILITY_DESIGN.md:
decides which open error_event rows are worth promoting to a real incident,
and at what severity. Called on a schedule by ErrorThresholdEvaluationWorkflow
(Pattern 3, Temporal Schedule) — zero Temporal imports here.

Classification rules are now PA-editable, read from severity_classification_rule
(domain=ERROR_OBSERVABILITY) via SeverityPolicyService — see
prana-docs/SEVERITY_SLA_POLICY_DESIGN.md. Formerly hardcoded Python constants;
migration 041 seeds the rule set with the original values unchanged.

Note: source_detail holds whatever was actually recorded by
ErrorObservabilityService.record() — an HTTP route path, a Kafka consumer
class name, or a Temporal activity name — NOT a source file path.
"""
from typing import Any, Optional

from services.severity_policy_service import SeverityPolicyService


class ErrorThresholdService:

    def __init__(self, db) -> None:
        self._db = db
        self._policy = SeverityPolicyService(db)

    async def evaluate_promotions(self) -> dict[str, Any]:
        rows = await self._db.fetch(
            "SELECT error_id, source_detail, occurrence_count, first_seen_at, last_seen_at "
            "FROM error_event WHERE status IN ('NEW', 'ACKNOWLEDGED') AND linked_incident_id IS NULL"
        )

        promoted = []
        for row in rows:
            severity = await self._classify(row)
            if severity:
                incident_id = await self.promote_to_incident_via_error_observability(
                    error_id=str(row["error_id"]), severity=severity,
                )
                promoted.append({
                    "error_id": str(row["error_id"]), "incident_id": incident_id, "severity": severity,
                })

        return {"evaluated": len(rows), "promoted": promoted}

    async def promote_to_incident_via_error_observability(self, *, error_id: str, severity: str) -> str:
        from services.error_observability_service import ErrorObservabilityService
        return await ErrorObservabilityService(self._db).promote_to_incident(
            error_id=error_id, severity=severity,
        )

    async def _classify(self, row: dict) -> Optional[str]:
        source_detail = row["source_detail"] or ""
        occurrence_count = row["occurrence_count"]
        span = row["last_seen_at"] - row["first_seen_at"]
        span_minutes = span.total_seconds() / 60

        return await self._policy.resolve_severity(
            domain="ERROR_OBSERVABILITY",
            value=source_detail,
            occurrence_count=occurrence_count,
            span_minutes=span_minutes,
        )
