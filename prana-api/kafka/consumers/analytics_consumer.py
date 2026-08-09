"""
AnalyticsConsumer — prana.analytics.events

Handles async analytics work that must not block the ingest path.

Events handled:
  DOC_ROUTED  → trigger InsightRefreshWorkflow (low-priority task queue)
              → trigger MarketCompWorkflow (insight-queue) — added 2026-08-06,
                was fully implemented (services/analytics_service.py's
                build_market_comp) but never started by anything
              → trigger CareerInsightWorkflow (insight-queue) — added
                2026-08-07, build_career_insight raised NotImplementedError
                until prana-ai's /pipeline/career-insight endpoint existed
              → trigger SkillGapWorkflow (insight-queue) — added 2026-08-07,
                gated to CAREER_LETTER_DOC_TYPES only (unlike the three
                triggers above, which fire on every DOC_ROUTED): career_event
                never gets a row for SALARY_SLIP/FORM_16/PF_ACKNOWLEDGEMENT
                (prana-ai/pipeline/stage06_route.py's _doc_type_to_event maps
                them to None), so firing on those would be pointless
              → invalidate vault completeness Redis cache for tenant
"""
import json
import logging

from aiokafka import AIOKafkaConsumer
from redis.asyncio import Redis

from config import Settings

log = logging.getLogger(__name__)

GROUP_ID = "prana-analytics-consumer"
INSIGHT_TASK_QUEUE = "insight-queue"

# Doc types that produce a career_event row (pipeline/stage06_route.py's
# _doc_type_to_event) — the only ones SkillGapWorkflow has anything to read.
CAREER_LETTER_DOC_TYPES = {
    "OFFER_LETTER", "APPOINTMENT_LETTER", "JOINING_LETTER",
    "INCREMENT_LETTER", "PROMOTION_LETTER",
    "RELIEVING_LETTER", "EXPERIENCE_LETTER",
}


class AnalyticsConsumer:
    def __init__(self, settings: Settings, temporal_client, redis: Redis) -> None:
        self._temporal = temporal_client
        self._redis    = redis
        self._consumer = AIOKafkaConsumer(
            "prana.analytics.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("AnalyticsConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    if etype == "DOC_ROUTED":
                        await self._handle_doc_routed(event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        None, consumer_name="AnalyticsConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("AnalyticsConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _handle_doc_routed(self, event: dict) -> None:
        tenant_id    = event["tenant_id"]
        employee_uuid = event.get("employee_uuid")
        doc_id        = event["document_id"]
        doc_type      = event.get("doc_type")

        # Invalidate vault completeness cache so next request recalculates
        await self._redis.delete(f"vault:{tenant_id}")

        # Trigger insight refresh as fire-and-forget (low-priority queue)
        if self._temporal and employee_uuid:
            from workflows.insight_refresh import InsightRefreshWorkflow
            try:
                await self._temporal.start_workflow(
                    InsightRefreshWorkflow.run,
                    {"document_id": doc_id, "tenant_id": tenant_id, "employee_uuid": employee_uuid},
                    id=f"insight-{doc_id}",
                    task_queue=INSIGHT_TASK_QUEUE,
                )
            except Exception as exc:
                if "already" not in str(exc).lower():
                    log.exception("InsightRefreshWorkflow start failed doc_id=%s", doc_id)

            # Per-employee (not per-document) workflow ID — a burst of uploads
            # for one employee collapses to the latest recompute rather than
            # queuing N runs. grade/department rarely change per-document, but
            # a PROMOTION_LETTER/INCREMENT_LETTER can, so recomputing on every
            # ROUTED document (same convention as InsightRefreshWorkflow above)
            # rather than inventing a separate cadence.
            from workflows.intelligence import MarketCompWorkflow
            try:
                await self._temporal.start_workflow(
                    MarketCompWorkflow.run,
                    {"employee_uuid": employee_uuid, "tenant_id": tenant_id},
                    id=f"market-comp-{employee_uuid}",
                    task_queue=INSIGHT_TASK_QUEUE,
                )
            except Exception as exc:
                if "already" not in str(exc).lower():
                    log.exception("MarketCompWorkflow start failed employee_uuid=%s", employee_uuid)

            # Per-employee workflow ID, same collapsing-burst rationale as
            # MarketCompWorkflow above.
            from workflows.intelligence import CareerInsightWorkflow
            try:
                await self._temporal.start_workflow(
                    CareerInsightWorkflow.run,
                    {"employee_uuid": employee_uuid, "tenant_id": tenant_id},
                    id=f"career-insight-{employee_uuid}",
                    task_queue=INSIGHT_TASK_QUEUE,
                )
            except Exception as exc:
                if "already" not in str(exc).lower():
                    log.exception("CareerInsightWorkflow start failed employee_uuid=%s", employee_uuid)

            if doc_type in CAREER_LETTER_DOC_TYPES:
                from workflows.intelligence import SkillGapWorkflow
                try:
                    await self._temporal.start_workflow(
                        SkillGapWorkflow.run,
                        {"employee_uuid": employee_uuid, "tenant_id": tenant_id},
                        id=f"skill-gap-{employee_uuid}",
                        task_queue=INSIGHT_TASK_QUEUE,
                    )
                except Exception as exc:
                    if "already" not in str(exc).lower():
                        log.exception("SkillGapWorkflow start failed employee_uuid=%s", employee_uuid)
