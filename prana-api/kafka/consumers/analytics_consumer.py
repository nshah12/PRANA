"""
AnalyticsConsumer — prana.analytics.events

Handles async analytics work that must not block the ingest path.

Events handled:
  DOC_ROUTED  → trigger InsightRefreshWorkflow (low-priority task queue)
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
                except Exception:
                    log.exception("AnalyticsConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _handle_doc_routed(self, event: dict) -> None:
        tenant_id    = event["tenant_id"]
        employee_uuid = event.get("employee_uuid")
        doc_id        = event["document_id"]

        # Invalidate vault completeness cache so next request recalculates
        await self._redis.delete(f"vault:{tenant_id}")

        # Trigger insight refresh as fire-and-forget (low-priority queue)
        if self._temporal and employee_uuid:
            from workflows.document_pipeline import InsightRefreshWorkflow
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
