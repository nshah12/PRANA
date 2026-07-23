"""
SMSConsumer — prana.notifications.sms

Real channel adapter: calls SMSService.send() directly (config-driven vendor
chain — AWS SNS/Exotel/MSG91 — + circuit breaker, see services/sms_service.py)
and writes notification_log itself. No longer routes through
NotificationService.notify() (which stubbed SMS entirely — see
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §1, §7 step 4).
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService
from services.notification_log import write_notification_log
from services.notification_service import _SUBJECT_MAP
from services.sms_service import SMSService

log = logging.getLogger(__name__)
GROUP_ID = "prana-sms-consumer"


class SMSConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None) -> None:
        self._settings = settings
        self._pool = db_pool
        self._redis = redis
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
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="SMSConsumer", exc=exc, event_type=event.get("event_type"),
                    )
                    log.exception("SMSConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        phone       = event.get("recipient_phone")
        template_id = event.get("template_id")
        if not phone or not template_id:
            log.warning("SMSConsumer: missing phone or template_id event_type=%s", event.get("event_type"))
            return
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            config  = ConfigService(conn, self._redis)
            breaker = CircuitBreaker(self._redis, config)
            sms_svc = SMSService(self._settings, config, breaker)

            template_data = event.get("template_data") or {}
            body = _SUBJECT_MAP.get(template_id, "PRANA Notification")
            sent, error = await sms_svc.send(
                to=phone, body=body, tenant_id=event.get("tenant_id"),
            )
            await write_notification_log(
                conn,
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "SMS"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                recipient_phone=phone,
                channel="SMS",
                template_id=template_id,
                template_data=template_data,
                status="SENT" if sent else "FAILED",
                error_message=error,
            )
            masked = phone[:6] + "****"
            if sent:
                log.info("SMSConsumer: dispatched %s → %s", template_id, masked)
            else:
                log.error("SMSConsumer: dispatch failed %s → %s error=%s", template_id, masked, error)
