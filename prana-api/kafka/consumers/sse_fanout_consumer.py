"""
SSEFanoutConsumer — prana.pipeline.events → Redis Pub/Sub → browser SSE

Replaces the broken DB-poll pattern in GET /ingest/status/{document_id}.

Flow:
  Temporal stage activity publishes STAGE_CHANGED to prana.pipeline.events
      → SSEFanoutConsumer receives it
          → redis.publish("sse:doc:{document_id}", json payload)
              → SSE endpoint's asyncio subscriber reads it
                  → yields SSE frame to browser

Redis channel TTL: ephemeral — no TTL on channels; subscribers connect/disconnect naturally.
"""
import json
import logging

from aiokafka import AIOKafkaConsumer
from redis.asyncio import Redis

from config import Settings

log = logging.getLogger(__name__)

GROUP_ID = "prana-sse-fanout"


class SSEFanoutConsumer:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._redis = redis
        self._consumer = AIOKafkaConsumer(
            "prana.pipeline.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="latest",   # SSE is real-time only; don't replay history
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("SSEFanoutConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                doc_id = event.get("document_id")
                if not doc_id:
                    continue
                try:
                    channel = f"sse:doc:{doc_id}"
                    payload = json.dumps({
                        "document_id":     doc_id,
                        "pipeline_status": event.get("pipeline_status"),
                        "event_type":      event.get("event_type"),
                        "occurred_at":     event.get("occurred_at"),
                    })
                    await self._redis.publish(channel, payload)
                except Exception:
                    log.exception("SSEFanoutConsumer publish failed doc_id=%s", doc_id)
        finally:
            await self._consumer.stop()
