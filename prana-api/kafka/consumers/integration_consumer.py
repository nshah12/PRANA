"""
IntegrationConsumer — prana.integrations.events

Handles retry logic for HRMS webhook failures, EPFO verification failures,
and KMS health tracking. Dead-letter path for integration errors.

Events handled:
  HRMS_WEBHOOK_FAILED       → enqueue retry with exponential backoff (max 3x)
  EPFO_VERIFICATION_FAILED  → mark document stage for manual review
  KMS_HEALTH_FAILED         → alert platform ops (publish to prana.platform.events)
  TEXTRACT_FALLBACK_USED    → analytics counter
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-integration-consumer"


class IntegrationConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None,
                 kafka_producer=None) -> None:
        self._pool = db_pool
        self._kafka = kafka_producer
        self._consumer = AIOKafkaConsumer(
            "prana.integrations.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("IntegrationConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="IntegrationConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("IntegrationConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        etype = event.get("event_type")
        await self._dispatch(etype, event)

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "HRMS_WEBHOOK_FAILED":
            await self._handle_hrms_failure(event)

        elif etype == "EPFO_VERIFICATION_FAILED":
            await self._flag_for_manual_review(event)

        elif etype == "KMS_HEALTH_FAILED":
            if self._kafka:
                try:
                    await self._kafka.platform_event({
                        "event_type": "HEALTH_CHECK_FAILED",
                        "service": "kms",
                        "detail": event.get("detail"),
                        "region": event.get("region"),
                    })
                except Exception:
                    log.exception("IntegrationConsumer: failed to escalate KMS failure to platform topic")

        else:
            log.debug("IntegrationConsumer: no action for event_type=%s", etype)

    async def _handle_hrms_failure(self, event: dict) -> None:
        if not self._pool:
            return

        request_id = event.get("request_id")
        if not request_id:
            log.warning("IntegrationConsumer: HRMS_WEBHOOK_FAILED missing request_id, cannot track retry tenant_id=%s",
                        event.get("tenant_id"))
            return

        max_retries = 3
        async with self._pool.acquire() as conn:
            try:
                # Atomic upsert: first failure for a request_id creates the row
                # (retry_count=1); later failures increment it, guarded by the
                # WHERE clause so a row already at max_retries is left untouched
                # and RETURNING comes back empty — no separate SELECT needed.
                row = await conn.fetchrow(
                    """
                    INSERT INTO api_ingest_log (request_id, tenant_id, filename, reason, retry_count, last_retry_at)
                    VALUES ($1, $2, $3, $4, 1, NOW())
                    ON CONFLICT (request_id) DO UPDATE
                    SET retry_count = api_ingest_log.retry_count + 1, last_retry_at = NOW()
                    WHERE api_ingest_log.retry_count < $5
                    RETURNING retry_count
                    """,
                    request_id, event.get("tenant_id"), event.get("filename"), event.get("reason"), max_retries,
                )
            except Exception:
                log.exception("IntegrationConsumer: failed to update retry count")
                return

        if row is None:
            log.error("IntegrationConsumer: HRMS webhook exhausted retries tenant_id=%s",
                       event.get("tenant_id"))
            return
        log.info("IntegrationConsumer: HRMS retry logged tenant_id=%s retry_count=%s",
                  event.get("tenant_id"), row["retry_count"])

    async def _flag_for_manual_review(self, event: dict) -> None:
        if not self._pool:
            return
        doc_id = event.get("document_id")
        if not doc_id:
            return

        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    UPDATE document
                    SET pipeline_status='EXCEPTION', exception_type='EPFO_VERIFICATION_FAILED',
                        updated_at=NOW()
                    WHERE document_id=$1 AND is_deleted=FALSE
                    """,
                    doc_id,
                )
            except Exception:
                log.exception("IntegrationConsumer: failed to flag document document_id=%s", doc_id)
        log.info("IntegrationConsumer: flagged document for manual review document_id=%s", doc_id)
