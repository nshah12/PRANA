"""
StatutoryConsumer — prana.statutory.events

Handles labour law obligation events: notifications to CHRO/CFO,
starting escalation workflows on overdue obligations.

Events handled:
  OBLIGATION_DUE       → notify CHRO + CFO via portal bell
  OBLIGATION_OVERDUE   → start ObligationEscalationWorkflow + notify CISO + CFO (email)
  OBLIGATION_COMPLETED → log, update analytics
  GRATUITY_ELIGIBILITY_TRIGGERED → start GratuityCalculationWorkflow
  BONUS_CALCULATION_DUE          → start BonusCalculationWorkflow
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
                except Exception:
                    log.exception("StatutoryConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "OBLIGATION_DUE":
            await self._notify_due(event)

        elif etype == "OBLIGATION_OVERDUE":
            await self._handle_overdue(event)

        elif etype == "GRATUITY_ELIGIBILITY_TRIGGERED":
            await self._start_workflow("GratuityCalculationWorkflow",
                                       f"gratuity-{event.get('employee_uuid')}-{event.get('tenant_id')}",
                                       event, "prana-compliance")

        elif etype == "BONUS_CALCULATION_DUE":
            await self._start_workflow("BonusCalculationWorkflow",
                                       f"bonus-{event.get('tenant_id')}-{event.get('period')}",
                                       event, "prana-compliance")

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
                    "event_type":   "OBLIGATION_DUE",
                    "recipient_id": str(row["oa_user_id"]),
                    "template_id":  "OBLIGATION_DUE",
                    "tenant_id":    tenant_id,
                    "payload":      payload,
                })
            log.info("StatutoryConsumer: published OBLIGATION_DUE bell notifications tenant_id=%s count=%d",
                     tenant_id, len(rows))
        except Exception:
            log.exception("StatutoryConsumer: failed to publish obligation_due notifications")

    async def _handle_overdue(self, event: dict) -> None:
        await self._start_workflow("ObligationEscalationWorkflow",
                                   f"obligation-escalate-{event.get('obligation_id')}",
                                   event, "prana-compliance")

    async def _start_workflow(self, workflow: str, wf_id: str, event: dict, task_queue: str) -> None:
        if not self._temporal:
            return
        try:
            await self._temporal.start_workflow(
                workflow, event, id=wf_id, task_queue=task_queue,
            )
            log.info("StatutoryConsumer: started %s workflow_id=%s", workflow, wf_id)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                log.exception("StatutoryConsumer: failed to start %s", workflow)
                raise
