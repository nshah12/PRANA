"""
PushConsumer — prana.notifications.push

Real channel adapter (2026-08-06 — was the last consumer still on the
pre-Communication-Hub NotificationService.notify() stub; every other channel
consumer was already upgraded during the Hub build). Calls PushService.send()
directly (Expo push, vendor chain + circuit breaker, see
services/push_service.py) and writes notification_log itself.

Fans out to every non-revoked, non-null device_credential.push_token the
recipient has registered — an employee can have multiple devices. A
DeviceNotRegistered error from Expo clears that specific dead token so a
stale device stops being retried forever.

No PA-editable credential fields exist for push (Expo's basic push API needs
no token) — unlike email/sms/whatsapp/ivr, this consumer does not call
CommunicationSettingsService.get_effective_settings(); there's nothing for
it to override.
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
from services.notification_service import _SUBJECT_MAP, _check_template_data
from services.push_service import PushService

log = logging.getLogger(__name__)
GROUP_ID = "prana-push-consumer"


class PushConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, redis=None,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._redis = redis
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
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="PushConsumer", exc=exc, event_type=event.get("event_type"),
                    )
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
            devices = await conn.fetch(
                "SELECT device_credential_id, push_token FROM device_credential "
                "WHERE employee_user_id=$1 AND revoked=FALSE AND push_token IS NOT NULL",
                recipient_id,
            )
            if not devices:
                log.info("PushConsumer: no registered device for recipient_id=%s", recipient_id)
                return

            config  = ConfigService(conn, self._redis)
            breaker = CircuitBreaker(self._redis, config)
            push_svc = PushService(self._settings, config, breaker)

            tenant_id = event.get("tenant_id")
            template_data = event.get("template_data") or {}
            try:
                _check_template_data(template_data)
            except ValueError as exc:
                log.error("PushConsumer: blocked template_data with PAN/salary key event_type=%s err=%s",
                          event.get("event_type"), exc)
                await write_notification_log(
                    conn,
                    tenant_id=tenant_id,
                    event_type=event.get("event_type", "PUSH"),
                    recipient_id=str(recipient_id),
                    recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                    channel="PUSH",
                    template_id=template_id,
                    template_data=template_data,
                    status="BLOCKED",
                    error_message=str(exc),
                )
                return
            title = "PRANA"
            body = _SUBJECT_MAP.get(template_id, "You have a new update in PRANA.")

            any_sent = False
            last_error: Optional[str] = None
            for row in devices:
                sent, error = await push_svc.send(
                    to=row["push_token"], title=title, body=body,
                    data={"template_id": template_id}, tenant_id=tenant_id,
                )
                if sent:
                    any_sent = True
                elif error == "DeviceNotRegistered":
                    await conn.execute(
                        "UPDATE device_credential SET push_token=NULL WHERE device_credential_id=$1",
                        row["device_credential_id"],
                    )
                else:
                    last_error = error

            await write_notification_log(
                conn,
                tenant_id=tenant_id,
                event_type=event.get("event_type", "PUSH"),
                recipient_id=str(recipient_id),
                recipient_type=str(event.get("recipient_type", "EMPLOYEE")).upper(),
                channel="PUSH",
                template_id=template_id,
                template_data=template_data,
                status="SENT" if any_sent else "FAILED",
                error_message=None if any_sent else last_error,
            )
            masked = str(recipient_id)[:8]
            if any_sent:
                log.info("PushConsumer: dispatched %s → recipient=%s (%d device(s))",
                          template_id, masked, len(devices))
            else:
                log.error("PushConsumer: dispatch failed %s → recipient=%s error=%s",
                           template_id, masked, last_error)
