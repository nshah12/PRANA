"""
PushConsumer — prana.notifications.push

Dispatches push notifications via FCM (Android) / APNs (iOS).
Push tokens stored in employee_device.push_token.
If push fails (token expired), falls back to SMS via notification_service.
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.notification_service import NotificationService, Channel, RecipientType

log = logging.getLogger(__name__)
GROUP_ID = "prana-push-consumer"


class PushConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.push",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("PushConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("PushConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        recipient_id = event.get("recipient_id")
        template_id  = event.get("template_id")
        if not recipient_id or not template_id:
            log.warning("PushConsumer: missing recipient_id or template_id event_type=%s", event.get("event_type"))
            return
        try:
            await self._send_push(recipient_id, template_id, event)
        except Exception:
            log.exception("PushConsumer: _send_push failed recipient_id=%s", recipient_id)

    async def _send_push(self, recipient_id: str, template_id: str, event: dict) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            svc = NotificationService(db=conn)
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "PUSH"),
                recipient_id=str(recipient_id),
                recipient_type=RecipientType(event.get("recipient_type", "employee")),
                channel=Channel.PUSH,
                template_id=template_id,
                template_data=event.get("template_data") or {},
            )
            log.info("PushConsumer: dispatched %s → recipient=%s", template_id, str(recipient_id)[:8])
