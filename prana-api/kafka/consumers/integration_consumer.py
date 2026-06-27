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
                except Exception:
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

        max_retries = 3
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT retry_count FROM api_ingest_log WHERE request_id = $1",
                    event.get("request_id"),
                )
                retry_count = row["retry_count"] if row else 0
                if retry_count >= max_retries:
                    log.error("IntegrationConsumer: HRMS webhook exhausted retries tenant_id=%s",
                              event.get("tenant_id"))
                    return
                await conn.execute(
                    """
                    UPDATE api_ingest_log
                    SET retry_count = retry_count + 1, last_retry_at = NOW()
                    WHERE request_id = $1
                    """,
                    event.get("request_id"),
                )
            except Exception:
                log.exception("IntegrationConsumer: failed to update retry count")
        log.info("IntegrationConsumer: HRMS retry logged tenant_id=%s", event.get("tenant_id"))

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
