"""
IVRConsumer — prana.notifications.ivr (new channel)

Real channel adapter: calls IVRService.send() directly (Exotel/Ozonetel,
config-driven vendor chain + circuit breaker, see services/ivr_service.py)
and writes notification_log itself. Same shape as SMSConsumer/EmailConsumer.
See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5, §7 step 5.

template_id is passed through as the flow/campaign ID to play — each vendor
falls back to its own configured default if it doesn't recognize it, so this
works even before per-template IVR flows are individually provisioned.
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
from services.ivr_service import IVRService
from services.notification_log import write_notification_log

log = logging.getLogger(__name__)
GROUP_ID = "prana-ivr-consumer"


class IVRConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None, kms_service=None,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._redis = redis
        self._kms = kms_service
        self._consumer = AIOKafkaConsumer(
            "prana.notifications.ivr",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("IVRConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="IVRConsumer", exc=exc, event_type=event.get("event_type"),
                    )
                    log.exception("IVRConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        phone       = event.get("recipient_phone")
        template_id = event.get("template_id")
        if not phone or not template_id:
            log.warning("IVRConsumer: missing phone or template_id event_type=%s", event.get("event_type"))
            return
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            config   = ConfigService(conn, self._redis)
            breaker  = CircuitBreaker(self._redis, config)
            settings = self._settings
            if self._kms:
                kek_arn = resolve_platform_auth_kek_arn(self._settings)
                settings = await CommunicationSettingsService(conn).get_effective_settings(
                    self._settings, self._kms, kek_arn,
                )
            ivr_svc  = IVRService(settings, config, breaker)

            template_data = event.get("template_data") or {}
            sent, error = await ivr_svc.send(
                to=phone, body=template_id, tenant_id=event.get("tenant_id"),
            )
            await write_notification_log(
                conn,
                tenant_id=event.get("tenant_id"),
                event_type=event.get("event_type", "IVR"),
                recipient_id=str(event.get("recipient_id", "")),
                recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                recipient_phone=phone,
                channel="IVR",
                template_id=template_id,
                template_data=template_data,
                status="SENT" if sent else "FAILED",
                error_message=error,
            )
            masked = phone[:6] + "****"
            if sent:
                log.info("IVRConsumer: dispatched %s → %s", template_id, masked)
            else:
                log.error("IVRConsumer: dispatch failed %s → %s error=%s", template_id, masked, error)
