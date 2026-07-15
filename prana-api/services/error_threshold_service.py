"""
ErrorThresholdService — implements §5 of prana-docs/ERROR_OBSERVABILITY_DESIGN.md:
decides which open error_event rows are worth promoting to a real incident,
and at what severity. Called on a schedule by ErrorThresholdEvaluationWorkflow
(Pattern 3, Temporal Schedule) — zero Temporal imports here.

Classification rules (approved 2026-07-15, decisions 2 & 3):
  - Security/crypto-critical source (auth routes, TOTP, AuthConsumer, the
    audit-integrity activity) -> P1 on first occurrence.
  - Compliance-critical endpoint (DPDP, ingest) -> P2 once it has recurred
    3+ times within a 10-minute span.
  - Any other genuinely new fingerprint -> P2 on first occurrence (a bug
    nobody has seen before deserves a look even before a pattern forms).
  - Everything else -> P3 once it has recurred 10+ times within 15 minutes
    (suggests systemic breakage, not one flaky message).

Note: source_detail holds whatever was actually recorded by
ErrorObservabilityService.record() — an HTTP route path, a Kafka consumer
class name, or a Temporal activity name — NOT a source file path.
"""
import datetime
from typing import Any, Optional

_SECURITY_PATH_PREFIXES = ("/auth/", "/totp/")
_SECURITY_SOURCE_DETAILS = {"AuthConsumer", "verify_audit_integrity"}
_COMPLIANCE_PATH_PREFIXES = ("/v1/dpdp/", "/v1/ingest/")

_COMPLIANCE_WINDOW = datetime.timedelta(minutes=10)
_COMPLIANCE_THRESHOLD = 3
_NOISE_WINDOW = datetime.timedelta(minutes=15)
_NOISE_THRESHOLD = 10


class ErrorThresholdService:

    def __init__(self, db) -> None:
        self._db = db

    async def evaluate_promotions(self) -> dict[str, Any]:
        rows = await self._db.fetch(
            "SELECT error_id, source_detail, occurrence_count, first_seen_at, last_seen_at "
            "FROM error_event WHERE status IN ('NEW', 'ACKNOWLEDGED') AND linked_incident_id IS NULL"
        )

        promoted = []
        for row in rows:
            severity = self._classify(row)
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

    def _classify(self, row: dict) -> Optional[str]:
        source_detail = row["source_detail"] or ""
        occurrence_count = row["occurrence_count"]
        span = row["last_seen_at"] - row["first_seen_at"]

        if self._is_security_path(source_detail):
            return "P1"

        if self._is_compliance_path(source_detail):
            if occurrence_count >= _COMPLIANCE_THRESHOLD and span <= _COMPLIANCE_WINDOW:
                return "P2"
            return None

        if occurrence_count == 1:
            return "P2"

        if occurrence_count >= _NOISE_THRESHOLD and span <= _NOISE_WINDOW:
            return "P3"

        return None

    @staticmethod
    def _is_security_path(source_detail: str) -> bool:
        if source_detail in _SECURITY_SOURCE_DETAILS:
            return True
        return any(source_detail.startswith(p) for p in _SECURITY_PATH_PREFIXES)

    @staticmethod
    def _is_compliance_path(source_detail: str) -> bool:
        return any(source_detail.startswith(p) for p in _COMPLIANCE_PATH_PREFIXES)
