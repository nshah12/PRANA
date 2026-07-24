"""
WhatsAppConsumer — prana.notifications.whatsapp

Real channel adapter (first real implementation — was a stub before): calls
WhatsAppService.send() directly (real Meta Cloud API/WABA, vendor chain +
circuit breaker, see services/whatsapp_service.py) and writes
notification_log itself. No longer routes through NotificationService.notify().
See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4.

Respects employee_user.whatsapp_opt_out — never send if opted out.
template_id doubles as the Meta-approved WABA template name (1:1 naming
convention — Portal Admin must create a matching template in Meta Business
Manager for every NotificationTemplate routed to this channel).
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.communication_settings_service import CommunicationSettingsService
from services.config_service import ConfigService
from services.encryption_service import resolve_platform_auth_kek_arn
from services.notification_log import write_notification_log
from services.whatsapp_service import WhatsAppService

log = logging.getLogger(__name__)
GROUP_ID = "prana-whatsapp-consumer"


class WhatsAppConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None, kms_service=None,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._redis = redis
        self._kms = kms_service
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
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="WhatsAppConsumer", exc=exc, event_type=event.get("event_type"),
                    )
                    log.exception("WhatsAppConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
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
            config  = ConfigService(conn, self._redis)
            breaker = CircuitBreaker(self._redis, config)
            settings = self._settings
            if self._kms:
                kek_arn = resolve_platform_auth_kek_arn(self._settings)
                settings = await CommunicationSettingsService(conn).get_effective_settings(
                    self._settings, self._kms, kek_arn,
                )
            wa_svc  = WhatsAppService(settings, config, breaker)

            template_data = event.get("template_data") or {}
            # Ordered positional values for the WABA template's {{1}}, {{2}}, ...
            # placeholders — same order-preserving convention _build_email_body
            # already uses for email. The approved Meta template must be authored
            # with its placeholders in this same order (whatever order the event
            # publisher built template_data in) since there's no per-template
            # variable-name registry to map against.
            template_params = [str(v) for v in template_data.values()] or None
            sent, error = await wa_svc.send(
                to=phone, body=template_id, template_params=template_params,
                tenant_id=event.get("tenant_id"),
            )
            await write_notification_log(
                conn,
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "WHATSAPP"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                recipient_phone=phone,
                channel="WHATSAPP",
                template_id=template_id,
                template_data=template_data,
                status="SENT" if sent else "FAILED",
                error_message=error,
            )
            masked = phone[:6] + "****"
            if sent:
                log.info("WhatsAppConsumer: dispatched %s → %s", template_id, masked)
            else:
                log.error("WhatsAppConsumer: dispatch failed %s → %s error=%s", template_id, masked, error)
