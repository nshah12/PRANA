"""
WhatsAppConsumer — prana.notifications.whatsapp

Dispatches WhatsApp via WABA approved templates only.
Respects employee_user.whatsapp_opt_out — never send if opted out.
On failure → logs SMS_FALLBACK event (SMSConsumer picks it up from prana.notifications.sms).
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.notification_service import NotificationService, Channel, RecipientType

log = logging.getLogger(__name__)
GROUP_ID = "prana-whatsapp-consumer"


class WhatsAppConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.whatsapp",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("WhatsAppConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("WhatsAppConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            # Respect opt-out before doing anything
            recipient_id = event.get("recipient_id")
            if recipient_id:
                opt_out = await conn.fetchval(
                    "SELECT whatsapp_opt_out FROM employee_user WHERE employee_user_id=$1",
                    recipient_id,
                )
                if opt_out:
                    log.info("WhatsAppConsumer: skipped — whatsapp_opt_out=TRUE recipient_id=%s", recipient_id)
                    return
        try:
            await self._send_whatsapp(event)
        except Exception:
            log.exception("WhatsAppConsumer: _send_whatsapp failed event_type=%s", event.get("event_type"))

    async def _send_whatsapp(self, event: dict) -> None:
        phone       = event.get("recipient_phone")
        template_id = event.get("template_id")
        if not phone or not template_id:
            log.warning("WhatsAppConsumer: missing phone or template_id")
            return
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            svc = NotificationService(db=conn)
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "WHATSAPP"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=RecipientType(event.get("recipient_type", "employee")),
                recipient_phone=phone,
                channel=Channel.WHATSAPP,
                template_id=template_id,
                template_data=event.get("template_data") or {},
            )
            log.info("WhatsAppConsumer: dispatched %s → %s", template_id, phone[:6] + "****")
