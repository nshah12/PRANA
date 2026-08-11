"""
EmailConsumer — prana.notifications.email

Real channel adapter: calls EmailService.send_email() directly (config-driven
vendor chain + circuit breaker, see services/email_service.py) and writes
notification_log itself. No longer routes through NotificationService.notify()
— see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4.

Every event must have: recipient_email, template_id, tenant_id, recipient_id
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
from services.email_service import EmailService
from services.encryption_service import resolve_platform_auth_kek_arn
from services.notification_log import write_notification_log
from services.notification_service import _SUBJECT_MAP, _build_email_body, _check_template_data

log = logging.getLogger(__name__)
GROUP_ID = "prana-email-consumer"


class EmailConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None, kms_service=None,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._redis = redis
        self._kms = kms_service
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
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="EmailConsumer", exc=exc, event_type=event.get("event_type"),
                    )
                    log.exception("EmailConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        recipient_email = event.get("recipient_email")
        template_id     = event.get("template_id")
        if not recipient_email or not template_id:
            log.warning("EmailConsumer: missing recipient_email or template_id — skipping event_type=%s", event.get("event_type"))
            return
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            config  = ConfigService(conn, self._redis)
            breaker = CircuitBreaker(self._redis, config)
            settings = self._settings
            if self._kms:
                # PA-entered credentials (services/communication_settings_service.py)
                # actually override env config here — editing via the PA screen
                # would otherwise be cosmetic. No-ops if nothing is DB-stored.
                kek_arn = resolve_platform_auth_kek_arn(self._settings)
                settings = await CommunicationSettingsService(conn).get_effective_settings(
                    self._settings, self._kms, kek_arn,
                )
            email_svc = EmailService(settings, config, breaker)

            template_data = event.get("template_data") or {}
            try:
                _check_template_data(template_data)
            except ValueError as exc:
                log.error("EmailConsumer: blocked template_data with PAN/salary key event_type=%s err=%s",
                          event.get("event_type"), exc)
                await write_notification_log(
                    conn,
                    tenant_id=event.get("tenant_id"),
                    event_type=event.get("event_type", "EMAIL"),
                    recipient_id=str(event.get("recipient_id", "")),
                    recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                    recipient_email=recipient_email,
                    channel="EMAIL",
                    template_id=template_id,
                    template_data=template_data,
                    status="BLOCKED",
                    error_message=str(exc),
                )
                return
            sent, error = await email_svc.send_email(
                to=recipient_email,
                subject=_SUBJECT_MAP.get(template_id, "PRANA Notification"),
                body=_build_email_body(template_id, template_data),
                tenant_id=event.get("tenant_id"),
            )
            await write_notification_log(
                conn,
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "EMAIL"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                recipient_email=recipient_email,
                channel="EMAIL",
                template_id=template_id,
                template_data=template_data,
                status="SENT" if sent else "FAILED",
                error_message=error,
            )
            if sent:
                log.info("EmailConsumer: dispatched %s → %s", template_id, recipient_email)
            else:
                log.error("EmailConsumer: dispatch failed %s → %s error=%s", template_id, recipient_email, error)
