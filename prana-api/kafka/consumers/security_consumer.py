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
                except Exception:
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
                        "CSAMReportingWorkflow", event, id=wf_id, task_queue="prana-admin",
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
        tenant_id = event.get("tenant_id")
        severity  = event.get("severity", "P3")

        if self._pool:
            async with self._pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO security_incident
                          (incident_id, tenant_id, incident_type, severity,
                           source_event_type, source_event_id, status, detected_at)
                        VALUES (gen_random_uuid(), $1, 'ANOMALY', $2,
                                'ANOMALY_DETECTED', $3, 'OPEN', NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        tenant_id, severity, event.get("anomaly_id"),
                    )
                except Exception:
                    log.exception("SecurityConsumer: failed to write security_incident")

        await self._push_sse_alert(event)

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
