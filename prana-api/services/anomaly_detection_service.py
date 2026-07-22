"""
AnomalyDetectionService — real implementation behind workflows/security.py's
run_anomaly_detection_batch (previously an unimplemented stub — see
prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3 for the full design and the
schema-investigation findings that grounded each rule).

6 detection rules, each following the same shape:
  1. Read this rule's own occurrence_threshold/window_minutes from
     severity_classification_rule (domain=ANOMALY_RULE) via
     SeverityPolicyService.get_rule_threshold — PA-editable, not hardcoded.
     If the rule is missing/deactivated, skip detection entirely rather than
     fall back to a guessed threshold.
  2. Query for candidates using that threshold.
  3. Skip anyone who already has an OPEN anomaly_event for this rule (dedup —
     batch runs every few minutes, must not spam duplicate anomalies for an
     ongoing pattern).
  4. Resolve severity via SeverityPolicyService.resolve_severity and write
     anomaly_event.
  5. Publish security_event with the severity already resolved — this is what
     fixes the security_consumer.py (P3) / notif_consumer.py (P2) default
     disagreement at the source, not just downstream.

Zero Temporal imports — called from workflows/security.py's
run_anomaly_detection_batch activity via an ad-hoc connection, same pattern as
services/audit_integrity_service.py.
"""
import datetime
import math
import uuid
from typing import Any, Optional

from services.severity_policy_service import SeverityPolicyService

_DOMAIN = "ANOMALY_RULE"
# document_access_log.actor_type values OA_OPERATOR/OA_OPERATOR_ELEVATED/OA_ADMIN all
# map to the oa_user table; THIRD_PARTY (HRMS API key) has no local lockable account.
_OA_USER_TYPE = "oa_user"


class AnomalyDetectionService:

    def __init__(self, db, kafka=None) -> None:
        self._db = db
        self._policy = SeverityPolicyService(db)
        self._kafka = kafka

    async def run_batch(self) -> dict[str, Any]:
        counts = {
            "BULK_DOC_ACCESS":    await self.detect_bulk_doc_access(),
            "BRUTE_FORCE":        await self.detect_brute_force(),
            "OFF_HOURS_ACCESS":   await self.detect_off_hours_access(),
            "IMPOSSIBLE_TRAVEL":  await self.detect_impossible_travel(),
            "SHARE_ENUM":         await self.detect_share_enum(),
            "PRE_EXIT_BULK":      await self.detect_pre_exit_bulk(),
        }
        return {"total_detected": sum(counts.values()), "by_rule": counts}

    # ── BULK_DOC_ACCESS ──────────────────────────────────────────────────────

    async def detect_bulk_doc_access(self) -> int:
        rule = "BULK_DOC_ACCESS"
        threshold = await self._policy.get_rule_threshold(domain=_DOMAIN, match_value=rule)
        if not threshold or not threshold["occurrence_threshold"]:
            return 0

        rows = await self._db.fetch(
            """
            SELECT actor_id, actor_type, tenant_id, COUNT(*) AS cnt,
                   MIN(accessed_at) AS first_at, MAX(accessed_at) AS last_at
              FROM document_access_log
             WHERE accessed_at >= NOW() - ($2 || ' minutes')::interval
               AND actor_type IN ('OA_OPERATOR', 'OA_OPERATOR_ELEVATED', 'OA_ADMIN', 'THIRD_PARTY')
               AND actor_id IS NOT NULL
             GROUP BY actor_id, actor_type, tenant_id
            HAVING COUNT(*) >= $1
            """,
            threshold["occurrence_threshold"], threshold["window_minutes"],
        )

        written = 0
        for row in rows:
            if await self._has_open_anomaly(rule, actor_id=row["actor_id"]):
                continue
            span_minutes = (row["last_at"] - row["first_at"]).total_seconds() / 60
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=row["tenant_id"], actor_id=row["actor_id"],
                occurrence_count=row["cnt"], span_minutes=span_minutes,
                metadata={"occurrence_count": row["cnt"]},
                actor_user_type=_OA_USER_TYPE if row["actor_type"] != "THIRD_PARTY" else None,
            )
        return written

    # ── BRUTE_FORCE ──────────────────────────────────────────────────────────

    async def detect_brute_force(self) -> int:
        rule = "BRUTE_FORCE"
        threshold = await self._policy.get_rule_threshold(domain=_DOMAIN, match_value=rule)
        if not threshold or not threshold["occurrence_threshold"]:
            return 0

        rows = await self._db.fetch(
            """
            SELECT user_id, user_type, tenant_id, COUNT(*) AS cnt,
                   MIN(attempted_at) AS first_at, MAX(attempted_at) AS last_at
              FROM login_attempt_log
             WHERE attempted_at >= NOW() - ($2 || ' minutes')::interval
               AND outcome = 'FAILED'
             GROUP BY COALESCE(user_id::text, identifier_hash), tenant_id, user_id, user_type
            HAVING COUNT(*) >= $1
            """,
            threshold["occurrence_threshold"], threshold["window_minutes"],
        )

        written = 0
        for row in rows:
            if await self._has_open_anomaly(rule, actor_id=row["user_id"]):
                continue
            span_minutes = (row["last_at"] - row["first_at"]).total_seconds() / 60
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=row["tenant_id"], actor_id=row["user_id"],
                occurrence_count=row["cnt"], span_minutes=span_minutes,
                metadata={"occurrence_count": row["cnt"]},
                actor_user_type=row["user_type"] if row["user_id"] else None,
            )
        return written

    # ── OFF_HOURS_ACCESS ─────────────────────────────────────────────────────

    async def detect_off_hours_access(self) -> int:
        rule = "OFF_HOURS_ACCESS"
        threshold = await self._policy.get_rule_threshold(domain=_DOMAIN, match_value=rule)
        if threshold is None:
            return 0

        start_hour = await self._get_config_int("off_hours_start_hour", 22)
        end_hour = await self._get_config_int("off_hours_end_hour", 6)

        rows = await self._db.fetch(
            """
            SELECT access_id, actor_id, tenant_id, accessed_at
              FROM document_access_log
             WHERE accessed_at >= NOW() - INTERVAL '30 minutes'
               AND actor_type IN ('OA_OPERATOR', 'OA_OPERATOR_ELEVATED', 'OA_ADMIN')
               AND (
                     EXTRACT(HOUR FROM accessed_at AT TIME ZONE 'Asia/Kolkata') >= $1
                  OR EXTRACT(HOUR FROM accessed_at AT TIME ZONE 'Asia/Kolkata') < $2
               )
            """,
            start_hour, end_hour,
        )

        written = 0
        for row in rows:
            if await self._has_open_anomaly_for_metadata(rule, "access_id", str(row["access_id"])):
                continue
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=row["tenant_id"], actor_id=row["actor_id"],
                occurrence_count=1, span_minutes=0,
                metadata={"access_id": str(row["access_id"]), "accessed_at": row["accessed_at"].isoformat()},
            )
        return written

    # ── IMPOSSIBLE_TRAVEL ────────────────────────────────────────────────────

    async def detect_impossible_travel(self) -> int:
        rule = "IMPOSSIBLE_TRAVEL"
        speed_threshold = await self._get_config_int("impossible_travel_speed_kmh", 900)

        rows = await self._db.fetch(
            """
            WITH recent AS (
                SELECT attempt_id, user_id, tenant_id, attempted_at, geo_lat, geo_lon,
                       LAG(attempted_at) OVER (PARTITION BY user_id ORDER BY attempted_at) AS prev_at,
                       LAG(geo_lat) OVER (PARTITION BY user_id ORDER BY attempted_at) AS prev_lat,
                       LAG(geo_lon) OVER (PARTITION BY user_id ORDER BY attempted_at) AS prev_lon
                  FROM login_attempt_log
                 WHERE outcome = 'SUCCESS' AND enrichment_status = 'DONE'
                   AND geo_lat IS NOT NULL AND geo_lon IS NOT NULL AND user_id IS NOT NULL
                   AND attempted_at >= NOW() - INTERVAL '2 days'
            )
            SELECT attempt_id, user_id, tenant_id, attempted_at, geo_lat, geo_lon,
                   prev_at, prev_lat, prev_lon
              FROM recent
             WHERE attempted_at >= NOW() - INTERVAL '30 minutes'
               AND prev_at IS NOT NULL
            """
        )

        written = 0
        for row in rows:
            hours = (row["attempted_at"] - row["prev_at"]).total_seconds() / 3600
            if hours <= 0:
                continue
            distance_km = _haversine_km(row["prev_lat"], row["prev_lon"], row["geo_lat"], row["geo_lon"])
            if distance_km < 50:
                continue  # GPS jitter at effectively the same location — not a signal
            speed_kmh = distance_km / hours
            if speed_kmh <= speed_threshold:
                continue
            if await self._has_open_anomaly_for_metadata(rule, "attempt_id", str(row["attempt_id"])):
                continue
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=row["tenant_id"], actor_id=row["user_id"],
                occurrence_count=1, span_minutes=0,
                metadata={"attempt_id": str(row["attempt_id"]),
                          "distance_km": round(distance_km, 1), "speed_kmh": round(speed_kmh, 1)},
            )
        return written

    # ── SHARE_ENUM ───────────────────────────────────────────────────────────

    async def detect_share_enum(self) -> int:
        rule = "SHARE_ENUM"
        threshold = await self._policy.get_rule_threshold(domain=_DOMAIN, match_value=rule)
        if not threshold or not threshold["occurrence_threshold"]:
            return 0

        rows = await self._db.fetch(
            """
            SELECT ip_address, COUNT(DISTINCT token_id) AS distinct_tokens,
                   MIN(attempted_at) AS first_at, MAX(attempted_at) AS last_at
              FROM share_otp_attempt
             WHERE success = FALSE
               AND attempted_at >= NOW() - ($2 || ' minutes')::interval
             GROUP BY ip_address
            HAVING COUNT(DISTINCT token_id) >= $1
            """,
            threshold["occurrence_threshold"], threshold["window_minutes"],
        )

        written = 0
        for row in rows:
            ip_str = str(row["ip_address"])
            if await self._has_open_anomaly_for_metadata(rule, "ip_address", ip_str):
                continue
            span_minutes = (row["last_at"] - row["first_at"]).total_seconds() / 60
            # Platform-level, not tenant-scoped — an IP enumerating share tokens isn't
            # attributable to a single tenant (it could span several).
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=None, actor_id=None,
                occurrence_count=row["distinct_tokens"], span_minutes=span_minutes,
                metadata={"ip_address": ip_str, "distinct_tokens": row["distinct_tokens"]},
            )
        return written

    # ── PRE_EXIT_BULK ────────────────────────────────────────────────────────

    async def detect_pre_exit_bulk(self) -> int:
        rule = "PRE_EXIT_BULK"
        threshold = await self._policy.get_rule_threshold(domain=_DOMAIN, match_value=rule)
        if not threshold or not threshold["occurrence_threshold"]:
            return 0

        lookahead_days = await self._get_config_int("pre_exit_bulk_lookahead_days", 30)

        rows = await self._db.fetch(
            """
            SELECT dal.employee_user_id, em.tenant_id, COUNT(*) AS cnt,
                   MIN(dal.accessed_at) AS first_at, MAX(dal.accessed_at) AS last_at
              FROM document_access_log dal
              JOIN employee_master em
                ON em.employee_user_id = dal.employee_user_id AND em.tenant_id = dal.tenant_id
             WHERE em.dol IS NOT NULL
               AND em.dol <= CURRENT_DATE + ($4 || ' days')::interval
               AND em.dol >= CURRENT_DATE - INTERVAL '7 days'
               AND dal.actor_type = 'EMPLOYEE'
               AND dal.accessed_at >= NOW() - ($2 || ' minutes')::interval
             GROUP BY dal.employee_user_id, em.tenant_id
            HAVING COUNT(*) >= $1
            """,
            threshold["occurrence_threshold"], threshold["window_minutes"], None, lookahead_days,
        )

        written = 0
        for row in rows:
            if await self._has_open_anomaly(rule, actor_id=row["employee_user_id"]):
                continue
            span_minutes = (row["last_at"] - row["first_at"]).total_seconds() / 60
            written += await self._raise_anomaly(
                rule_name=rule, tenant_id=row["tenant_id"], actor_id=row["employee_user_id"],
                occurrence_count=row["cnt"], span_minutes=span_minutes,
                metadata={"occurrence_count": row["cnt"]},
            )
        return written

    # ── Shared helpers ───────────────────────────────────────────────────────

    async def _has_open_anomaly(self, rule_name: str, *, actor_id: Optional[str]) -> bool:
        if not actor_id:
            return False
        row = await self._db.fetchval(
            "SELECT 1 FROM anomaly_event WHERE rule_name = $1 AND actor_id = $2 AND status = 'OPEN' LIMIT 1",
            rule_name, actor_id,
        )
        return bool(row)

    async def _has_open_anomaly_for_metadata(self, rule_name: str, key: str, value: str) -> bool:
        row = await self._db.fetchval(
            "SELECT 1 FROM anomaly_event WHERE rule_name = $1 AND status = 'OPEN' "
            "AND event_metadata->>$2 = $3 LIMIT 1",
            rule_name, key, value,
        )
        return bool(row)

    async def _raise_anomaly(
        self, *, rule_name: str, tenant_id: Optional[str], actor_id: Optional[str],
        occurrence_count: int, span_minutes: float, metadata: dict,
        actor_user_type: Optional[str] = None,
    ) -> int:
        import json
        severity = await self._policy.resolve_severity(
            domain=_DOMAIN, value=rule_name, occurrence_count=occurrence_count, span_minutes=span_minutes,
        )
        if not severity:
            return 0

        anomaly_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO anomaly_event
              (anomaly_id, tenant_id, rule_name, severity, actor_id, event_metadata, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'OPEN')
            """,
            anomaly_id, tenant_id, rule_name, severity, actor_id, json.dumps(metadata),
        )
        await self._publish_anomaly(
            anomaly_id=anomaly_id, tenant_id=tenant_id, rule_name=rule_name,
            severity=severity, actor_id=actor_id, actor_user_type=actor_user_type,
        )
        return 1

    async def _publish_anomaly(
        self, *, anomaly_id: str, tenant_id: Optional[str], rule_name: str,
        severity: str, actor_id: Optional[str], actor_user_type: Optional[str] = None,
    ) -> None:
        if not self._kafka:
            return
        # actor_user_type ("employee" | "oa_user") lets security_consumer.py's
        # auto-lock trigger know which table to lock — only BULK_DOC_ACCESS and
        # BRUTE_FORCE populate it; other rules pass None and are never auto-locked.
        await self._kafka.security_event({
            "event_type": "ANOMALY_DETECTED",
            "anomaly_id": anomaly_id,
            "tenant_id": tenant_id,
            "rule_name": rule_name,
            "severity": severity,
            "actor_id": actor_id,
            "actor_user_type": actor_user_type,
        })

    async def _get_config_int(self, key: str, default: int) -> int:
        value = await self._db.fetchval(
            "SELECT config_value FROM platform_config WHERE config_key = $1", key,
        )
        return int(value) if value is not None else default


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0  # Earth radius, km
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))
