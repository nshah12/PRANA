"""
SecurityConsumer — prana.security.events

Creates incidents, pushes real-time CISO dashboard alerts via Redis Pub/Sub,
and starts security-response workflows.

Events handled:
  ANOMALY_DETECTED          → create/update incident, push SSE to CISO dashboard
  CSAM_DETECTED             → start CSAMReportingWorkflow (POCSO Act obligation)
  CROSS_TENANT_UPLOAD_DETECTED → create security incident, notify PA Admin + CISO
  ACCOUNT_LOCKED            → push CISO SSE alert for P0/P1 severity
  SUSPICIOUS_LOGIN_DETECTED → push SSE alert
  KMS_HEALTH_FAILED         → push platform alert
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-security-consumer"

# Rule -> (auto-lock config flag, account_status_event.reason_code). Both flags
# ship OFF by default (prana-db/migrations/042) — see prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.3.
_AUTO_LOCK_RULES = {
    "BULK_DOC_ACCESS": ("bulk_access_auto_lock_enabled", "BULK_ACCESS_ANOMALY"),
    "BRUTE_FORCE":      ("brute_force_auto_lock_enabled", "BRUTE_FORCE_ANOMALY"),
}


class SecurityConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None,
                 temporal_client=None, redis=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._redis = redis
        self._consumer = AIOKafkaConsumer(
            "prana.security.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("SecurityConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="SecurityConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("SecurityConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "ANOMALY_DETECTED":
            await self._handle_anomaly(event)

        elif etype == "CSAM_DETECTED":
            if self._temporal:
                wf_id = f"csam-{event.get('document_id')}"
                try:
                    await self._temporal.start_workflow(
                        "CSAMReportingWorkflow", event, id=wf_id, task_queue="safety-queue",
                    )
                    log.critical("SecurityConsumer: started CSAMReportingWorkflow document_id=%s", event.get("document_id"))
                except Exception as exc:
                    if "already exists" not in str(exc).lower():
                        log.exception("SecurityConsumer: CSAM workflow failed to start")
                        raise

        elif etype in ("CROSS_TENANT_UPLOAD_DETECTED", "ACCOUNT_LOCKED", "SUSPICIOUS_LOGIN_DETECTED"):
            await self._push_sse_alert(event)

        else:
            log.debug("SecurityConsumer: no specific action for event_type=%s", etype)

    async def _handle_anomaly(self, event: dict) -> None:
        """Route into the real `incident` table (via IncidentService), never the
        nonexistent `security_incident` table this used to reference — see
        prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §4. Severity is trusted from the
        publisher if present (the anomaly-detection engine resolves it precisely
        with real occurrence/window context); otherwise resolved here via the
        same shared policy lookup notif_consumer.py uses, so the two consumers
        can no longer disagree on a default."""
        tenant_id = event.get("tenant_id")
        rule_name = event.get("rule_name") or event.get("anomaly_type") or "UNKNOWN_ANOMALY"
        severity  = event.get("severity")

        if self._pool:
            async with self._pool.acquire() as conn:
                try:
                    if not severity:
                        from services.severity_policy_service import SeverityPolicyService
                        severity = await SeverityPolicyService(conn).resolve_severity(
                            domain="ANOMALY_RULE", value=rule_name,
                        ) or "P3"

                    # Event-driven anomalies (published by an HTTP-handler-triggered guard,
                    # e.g. CROSS_TENANT_QUERY, or by change_role's PRIVILEGE_ESCALATION check)
                    # have no other writer for anomaly_event — persist it here, keyed by the
                    # publisher-supplied anomaly_id so Kafka redelivery can't duplicate rows.
                    anomaly_id = event.get("anomaly_id")
                    if anomaly_id:
                        await conn.execute(
                            """
                            INSERT INTO anomaly_event
                              (anomaly_id, tenant_id, rule_name, severity, actor_id, event_metadata, status)
                            VALUES ($1, $2, $3, $4, $5, $6, 'OPEN')
                            ON CONFLICT (anomaly_id) DO NOTHING
                            """,
                            anomaly_id, tenant_id, rule_name, severity, event.get("actor_id"),
                            json.dumps(event.get("event_metadata") or {}),
                        )

                    from services.incident_service import IncidentService
                    await IncidentService(conn).auto_create_for_anomaly(
                        anomaly_id=anomaly_id,
                        tenant_id=tenant_id,
                        rule_name=rule_name,
                        severity=severity,
                        assigned_ciso_id=None,
                    )
                except Exception:
                    log.exception("SecurityConsumer: failed to create incident for anomaly")

                try:
                    await self._maybe_auto_lock(conn, event, rule_name, tenant_id)
                except Exception:
                    log.exception("SecurityConsumer: failed to evaluate/start auto-lock rule=%s", rule_name)

        await self._push_sse_alert(event)

    async def _maybe_auto_lock(self, conn, event: dict, rule_name: str, tenant_id) -> None:
        """Config-gated auto-lock for BULK_DOC_ACCESS/BRUTE_FORCE anomalies — both
        flags ship OFF by default. See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.3."""
        rule_cfg = _AUTO_LOCK_RULES.get(rule_name)
        if not rule_cfg:
            return
        actor_user_type = event.get("actor_user_type")
        actor_id = event.get("actor_id")
        if actor_user_type not in ("employee", "oa_user") or not actor_id:
            return  # THIRD_PARTY actor or unresolved identifier — no lockable account

        config_key, reason_code = rule_cfg
        if not self._redis:
            return
        from services.config_service import ConfigService
        enabled = await ConfigService(conn, self._redis).get_bool(config_key, tenant_id)
        if not enabled or not self._temporal:
            return

        wf_id = f"policy-lock-{rule_name}-{actor_id}"
        try:
            await self._temporal.start_workflow(
                "PolicyLockWorkflow",
                {"user_type": actor_user_type, "user_id": actor_id,
                 "tenant_id": tenant_id, "reason_code": reason_code},
                id=wf_id, task_queue="secops-queue",
            )
            log.warning("SecurityConsumer: auto-locked account via PolicyLockWorkflow "
                        "rule=%s actor_id=%s", rule_name, actor_id)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                log.exception("SecurityConsumer: failed to start PolicyLockWorkflow for auto-lock")

    async def _push_sse_alert(self, event: dict) -> None:
        if not self._redis:
            return
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            return
        channel = f"sse:tenant:{tenant_id}:alerts"
        try:
            await self._redis.publish(channel, json.dumps(event))
            log.debug("SecurityConsumer: pushed SSE alert channel=%s", channel)
        except Exception:
            log.exception("SecurityConsumer: Redis publish failed channel=%s", channel)
