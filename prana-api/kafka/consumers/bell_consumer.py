"""
BellConsumer — prana.notifications.portal_bell

Pushes portal bell notifications to the portal via Redis Pub/Sub.
The portal's SSE endpoint subscribes to sse:user:{oa_user_id}:bells.
Also writes to notification_log for persistence (unread count badge).
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-bell-consumer"


class BellConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None) -> None:
        self._pool = db_pool
        self._redis = redis
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.portal_bell",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("BellConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("BellConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        recipient_id = event.get("recipient_id")
        if not recipient_id:
            log.warning("BellConsumer: missing recipient_id event_type=%s", event.get("event_type"))
            return

        # Push real-time via Redis Pub/Sub
        if self._redis:
            channel = f"sse:user:{recipient_id}:bells"
            try:
                await self._redis.publish(channel, json.dumps({
                    "event_type": event.get("event_type"),
                    "template_id": event.get("template_id"),
                    "template_data": event.get("template_data") or {},
                    "tenant_id": event.get("tenant_id"),
                }))
            except Exception:
                log.exception("BellConsumer: Redis publish failed recipient_id=%s", recipient_id)

        # Persist for unread count
        if self._pool:
            async with self._pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO notification_log
                          (notification_id, tenant_id, recipient_type, recipient_id,
                           channel, event_type, template_id, template_data, sent_at)
                        VALUES (gen_random_uuid(), $1, $2, $3, 'PORTAL_BELL', $4, $5, $6::jsonb, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        event.get("tenant_id"),
                        event.get("recipient_type", "oa_user"),
                        str(recipient_id),
                        event.get("event_type", "BELL"),
                        event.get("template_id", "GENERIC_BELL"),
                        json.dumps(event.get("template_data") or {}),
                    )
                except Exception:
                    log.exception("BellConsumer: notification_log write failed")

        log.info("BellConsumer: dispatched bell event_type=%s recipient=%s", event.get("event_type"), str(recipient_id)[:8])
