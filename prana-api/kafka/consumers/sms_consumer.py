"""
SMSConsumer — prana.notifications.sms

Dispatches SMS via MSG91 (primary) / Exotel (fallback).
Respects DND opt-out stored in employee_user.phone_opt_out.
Rate limit enforced via Redis before dispatch (3 OTP per 10 min already in CacheService).
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.notification_service import NotificationService, Channel, RecipientType

log = logging.getLogger(__name__)
GROUP_ID = "prana-sms-consumer"


class SMSConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.sms",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("SMSConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("SMSConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        phone       = event.get("recipient_phone")
        template_id = event.get("template_id")
        if not phone or not template_id:
            log.warning("SMSConsumer: missing phone or template_id event_type=%s", event.get("event_type"))
            return
        await self._send_sms(phone, template_id, event)

    async def _send_sms(self, phone: str, template_id: str, event: dict) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            svc = NotificationService(db=conn)
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "SMS"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=RecipientType(event.get("recipient_type", "employee")),
                recipient_phone=phone,
                channel=Channel.SMS,
                template_id=template_id,
                template_data=event.get("template_data") or {},
            )
            log.info("SMSConsumer: dispatched %s → %s", template_id, phone[:6] + "****")
