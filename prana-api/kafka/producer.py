"""
Kafka producer — thin wrapper around aiokafka.AIOKafkaProducer.

One instance per process, held on app.state.kafka_producer.
All events serialised as UTF-8 JSON.

Partition strategy:
  - prana.ingest.events   → partition by tenant_id  (ingest ordering per tenant)
  - prana.pipeline.events → partition by document_id (all stage changes in order)
  - prana.audit.events    → partition by tenant_id
  - prana.notifications   → partition by user_id
  - prana.analytics.events→ partition by tenant_id
"""
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from config import Settings

log = logging.getLogger(__name__)

TOPIC_INGEST    = "prana.ingest.events"
TOPIC_PIPELINE  = "prana.pipeline.events"
TOPIC_AUDIT     = "prana.audit.events"
TOPIC_NOTIF     = "prana.notifications"
TOPIC_ANALYTICS = "prana.analytics.events"


class KafkaPub:
    """Async Kafka producer. Start/stop managed by FastAPI lifespan."""

    def __init__(self, settings: Settings) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            acks="all",
            compression_type="gzip",
            enable_idempotence=True,
            max_batch_size=16384,
        )

    async def start(self) -> None:
        await self._producer.start()
        log.info("KafkaPub started")

    async def stop(self) -> None:
        await self._producer.stop()
        log.info("KafkaPub stopped")

    async def publish(self, topic: str, event: dict[str, Any], *, key: str | None = None) -> None:
        try:
            await self._producer.send_and_wait(topic, value=event, key=key)
        except KafkaError:
            log.exception("Kafka publish failed topic=%s event_type=%s", topic, event.get("event_type"))
            raise

    # ── Domain helpers ────────────────────────────────────────────────────────

    async def doc_ingested(self, event: dict) -> None:
        await self.publish(TOPIC_INGEST, event, key=event["tenant_id"])
        await self.publish(TOPIC_AUDIT,  event, key=event["tenant_id"])

    async def batch_uploaded(self, event: dict) -> None:
        await self.publish(TOPIC_INGEST, event, key=event["tenant_id"])
        await self.publish(TOPIC_AUDIT,  event, key=event["tenant_id"])

    async def stage_changed(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])

    async def doc_routed(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE,  event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,     event, key=event["tenant_id"])
        await self.publish(TOPIC_ANALYTICS, event, key=event["tenant_id"])
        await self.publish(TOPIC_NOTIF,     event, key=event.get("employee_uuid", event["tenant_id"]))

    async def exception_raised(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,    event, key=event["tenant_id"])
        await self.publish(TOPIC_NOTIF,    event, key=event["tenant_id"])

    async def exception_resolved(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,    event, key=event["tenant_id"])
