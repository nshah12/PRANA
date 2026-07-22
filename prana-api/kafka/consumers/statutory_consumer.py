"""
StatutoryConsumer — prana.statutory.events

Handles labour law obligation events: notifications to CHRO/CFO,
starting escalation workflows on overdue obligations.

Events handled:
  OBLIGATION_DUE       → notify CHRO + CFO via portal bell
  OBLIGATION_OVERDUE   → no workflow (never published — real overdue handling
                          already runs nightly via StatutoryComplianceWorkflow's
                          mark_overdue_obligations/notify_overdue_obligations,
                          Pattern 3 schedule in workflows/compliance.py)
  OBLIGATION_COMPLETED → log, update analytics
  GRATUITY_ELIGIBILITY_TRIGGERED → no workflow (never published; no
                          GratuityCalculationWorkflow exists — starting it
                          would queue a workflow no worker could ever execute)
  BONUS_CALCULATION_DUE          → no workflow (never published; no
                          BonusCalculationWorkflow exists — same reason)
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import get_kafka_producer

log = logging.getLogger(__name__)
GROUP_ID = "prana-statutory-consumer"


class StatutoryConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.statutory.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("StatutoryConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="StatutoryConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("StatutoryConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "OBLIGATION_DUE":
            await self._notify_due(event)

        elif etype == "OBLIGATION_OVERDUE":
            # No workflow: never published (labour_law.py only emits OBLIGATION_DUE/
            # OBLIGATION_COMPLETED) and "ObligationEscalationWorkflow" was never
            # @workflow.defn'd. Real overdue handling already runs nightly via
            # StatutoryComplianceWorkflow (workflows/compliance.py, Pattern 3 schedule).
            log.debug("StatutoryConsumer: OBLIGATION_OVERDUE has no event-driven handler "
                      "— see StatutoryComplianceWorkflow's nightly schedule")

        elif etype in ("GRATUITY_ELIGIBILITY_TRIGGERED", "BONUS_CALCULATION_DUE"):
            # No workflow: neither event is ever published, and neither
            # "GratuityCalculationWorkflow" nor "BonusCalculationWorkflow" is
            # @workflow.defn'd anywhere — starting either would silently queue a
            # workflow no worker could ever execute.
            log.debug("StatutoryConsumer: no workflow implemented yet for event_type=%s", etype)

        else:
            log.debug("StatutoryConsumer: no action for event_type=%s", etype)

    async def _notify_due(self, event: dict) -> None:
        if not self._pool:
            return
        tenant_id = event.get("tenant_id")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT oa_user_id FROM oa_user WHERE tenant_id=$1 AND role IN ('chro','cfo') AND status='ACTIVE'",
                tenant_id,
            )
        payload = {"obligation_id": event.get("obligation_id"),
                   "act": event.get("act"), "due_date": event.get("due_date")}
        try:
            kafka = await get_kafka_producer()
            for row in rows:
                await kafka.notify_bell({
                    "event_type":    "OBLIGATION_DUE",
                    "recipient_id":  str(row["oa_user_id"]),
                    "template_id":   "OBLIGATION_DUE",
                    "tenant_id":     tenant_id,
                    "template_data": payload,
                })
            log.info("StatutoryConsumer: published OBLIGATION_DUE bell notifications tenant_id=%s count=%d",
                     tenant_id, len(rows))
        except Exception:
            log.exception("StatutoryConsumer: failed to publish obligation_due notifications")
