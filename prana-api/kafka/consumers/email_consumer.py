"""
EmailConsumer — prana.notifications.email

Dispatches email via AWS SES. Replaces the email logic from old NotifConsumer.
Uses notification_log for dedup (ON CONFLICT DO NOTHING).

Every event must have: recipient_email, template_id, tenant_id, recipient_id
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.notification_service import NotificationService, Channel, RecipientType

log = logging.getLogger(__name__)
GROUP_ID = "prana-email-consumer"


class EmailConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.email",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("EmailConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("EmailConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        recipient_email = event.get("recipient_email")
        template_id     = event.get("template_id")
        if not recipient_email or not template_id:
            log.warning("EmailConsumer: missing recipient_email or template_id — skipping event_type=%s", event.get("event_type"))
            return
        try:
            await self._send_ses(recipient_email, template_id, event)
        except Exception:
            log.exception("EmailConsumer: _send_ses failed recipient_email=%s", recipient_email)

    async def _send_ses(self, recipient_email: str, template_id: str, event: dict) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            svc = NotificationService(db=conn)
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "EMAIL"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=RecipientType(event.get("recipient_type", "employee")),
                recipient_email=recipient_email,
                channel=Channel.EMAIL,
                template_id=template_id,
                template_data=event.get("template_data") or {},
            )
            log.info("EmailConsumer: dispatched %s → %s", template_id, recipient_email)
