"""
OAUserConsumer — prana.oa_users.events

Handles OA user lifecycle and elevation events.
Elevation workflow start was previously done directly in the HTTP handler;
that remains for the initial ElevationWorkflow start (direct Temporal call in HTTP is allowed
for signal-correlated workflows). This consumer handles everything else:
notifications, cache invalidation side-effects, audit-driven workflows.

Events handled:
  OA_USER_CREATED          → trigger welcome email notification
  OA_USER_LOCKED           → start AccountLockWorkflow
  ELEVATION_REQUESTED      → audit (workflow already started in HTTP handler)
  ELEVATION_APPROVED       → notify requestor (email)
  ELEVATION_DENIED         → notify requestor (email)
  ELEVATION_EXPIRED        → notify requestor (bell)
  OA_USER_ROLE_CHANGED     → (cache already invalidated via CacheInvalidationConsumer — audit only)
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import get_kafka_producer

log = logging.getLogger(__name__)
GROUP_ID = "prana-oa-user-consumer"


class OAUserConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.oa_users.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("OAUserConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("OAUserConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "OA_USER_CREATED":
            await self._notify_welcome(event)

        elif etype == "OA_USER_LOCKED":
            if self._temporal:
                wf_id = f"account-lock-oa-{event.get('oa_user_id')}"
                try:
                    await self._temporal.start_workflow(
                        "AccountLockWorkflow",
                        event,
                        id=wf_id,
                        task_queue="prana-admin",
                    )
                    log.info("OAUserConsumer: started AccountLockWorkflow workflow_id=%s", wf_id)
                except Exception as exc:
                    if "already exists" not in str(exc).lower():
                        log.exception("OAUserConsumer: failed to start AccountLockWorkflow")

        elif etype in ("ELEVATION_APPROVED", "ELEVATION_DENIED", "ELEVATION_EXPIRED"):
            await self._notify_elevation_result(etype, event)

        else:
            log.debug("OAUserConsumer: no action for event_type=%s", etype)

    async def _notify_welcome(self, event: dict) -> None:
        try:
            kafka = await get_kafka_producer()
            await kafka.notify_email({
                "event_type":    "OA_WELCOME",
                "recipient_id":  event.get("oa_user_id"),
                "recipient_email": event.get("email"),
                "template_id":   "OA_WELCOME",
                "tenant_id":     event.get("tenant_id"),
                "payload":       {"login_url": event.get("login_url", "https://prana.in/org/login")},
            })
            log.info("OAUserConsumer: published OA_WELCOME email oa_user_id=%s", event.get("oa_user_id"))
        except Exception:
            log.exception("OAUserConsumer: failed to publish OA_WELCOME email")

    async def _notify_elevation_result(self, etype: str, event: dict) -> None:
        recipient_id = event.get("requestor_id") or event.get("oa_user_id")
        payload = {"elevation_id": event.get("elevation_id"), "duration_hours": event.get("duration_hours")}
        try:
            kafka = await get_kafka_producer()
            if etype == "ELEVATION_EXPIRED":
                await kafka.notify_bell({
                    "event_type":   etype,
                    "recipient_id": recipient_id,
                    "template_id":  etype,
                    "tenant_id":    event.get("tenant_id"),
                    "payload":      payload,
                })
            else:
                await kafka.notify_email({
                    "event_type":   etype,
                    "recipient_id": recipient_id,
                    "template_id":  etype,
                    "tenant_id":    event.get("tenant_id"),
                    "payload":      payload,
                })
            log.info("OAUserConsumer: published %s notification recipient=%s", etype, recipient_id)
        except Exception:
            log.exception("OAUserConsumer: failed to publish %s notification", etype)
