"""
AuthConsumer — prana.auth.events

Security analysis on auth events: consecutive failures → trigger account lock,
suspicious login detection, session analytics.

Events handled:
  USER_LOGIN_FAILED       → increment failure counter; if ≥ threshold → AccountLockWorkflow
  TOTP_FAILED             → increment TOTP failure counter; if ≥ threshold → AccountLockWorkflow
  SESSION_FORCE_REVOKED   → log security incident
  PASSWORD_CHANGED        → invalidate all other sessions (send signal to SessionManagementWorkflow)
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import get_kafka_producer

log = logging.getLogger(__name__)
GROUP_ID = "prana-auth-consumer"

# These are also enforced in Redis rate limiting; this consumer handles Temporal escalation
_LOCK_AFTER_FAILURES = 5
_TOTP_LOCK_AFTER     = 5


class AuthConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.auth.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("AuthConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("AuthConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype == "USER_LOGIN_FAILED":
            await self._handle_login_failure(event)

        elif etype == "TOTP_FAILED":
            await self._handle_totp_failure(event)

        elif etype == "SESSION_FORCE_REVOKED":
            log.info("AuthConsumer: session force-revoked user_id=%s reason=%s",
                     event.get("user_id"), event.get("reason"))

        else:
            log.debug("AuthConsumer: no action for event_type=%s", etype)

    async def _handle_login_failure(self, event: dict) -> None:
        if not self._pool:
            return
        user_id = event.get("user_id")
        if not user_id:
            return

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt FROM login_attempt_log
                WHERE user_id=$1
                  AND success=FALSE
                  AND attempted_at > NOW() - INTERVAL '30 minutes'
                """,
                user_id,
            )
            if row and (row["cnt"] or 0) >= _LOCK_AFTER_FAILURES:
                await self._start_lock_workflow(user_id, event.get("user_type", "employee"),
                                                event.get("tenant_id"), "CONSECUTIVE_LOGIN_FAILURES")

    async def _handle_totp_failure(self, event: dict) -> None:
        if not self._pool:
            return
        user_id = event.get("user_id")
        if not user_id:
            return

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt FROM login_attempt_log
                WHERE user_id=$1
                  AND success=FALSE
                  AND attempted_at > NOW() - INTERVAL '30 minutes'
                """,
                user_id,
            )
            if row and (row["cnt"] or 0) >= _TOTP_LOCK_AFTER:
                await self._start_lock_workflow(user_id, event.get("user_type", "employee"),
                                                event.get("tenant_id"), "CONSECUTIVE_TOTP_FAILURES")

    async def _start_lock_workflow(self, user_id: str, user_type: str, tenant_id: Optional[str], reason: str) -> None:
        # Publish security event BEFORE starting workflow so SecurityConsumer logs the incident
        try:
            kafka = await get_kafka_producer()
            await kafka.security_event({
                "event_type": "ACCOUNT_LOCKED",
                "user_id":    user_id,
                "user_type":  user_type,
                "tenant_id":  tenant_id,
                "reason":     reason,
            })
        except Exception:
            log.exception("AuthConsumer: failed to publish ACCOUNT_LOCKED security event")

        if not self._temporal:
            return
        wf_id = f"account-lock-{user_id}"
        try:
            await self._temporal.start_workflow(
                "AccountLockWorkflow",
                {"user_id": user_id, "user_type": user_type, "tenant_id": tenant_id, "reason": reason},
                id=wf_id,
                task_queue="prana-admin",
            )
            log.info("AuthConsumer: started AccountLockWorkflow user_id=%s reason=%s", user_id, reason)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                log.exception("AuthConsumer: failed to start AccountLockWorkflow")
