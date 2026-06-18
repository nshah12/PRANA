"""
AuditConsumer — prana.audit.events

Writes every domain event to audit_event (immutable — no UPDATE/DELETE ever).
Runs independently so the HTTP handler never blocks on audit writes.

Subscribes to prana.audit.events which receives copies of:
  DOC_INGESTED, BATCH_UPLOADED, STAGE_CHANGED, DOC_ROUTED,
  EXCEPTION_RAISED, EXCEPTION_RESOLVED, EXCEPTION_DISMISSED,
  ELEVATION_APPROVED, ELEVATION_ENDED, ...

The event payload IS the audit metadata — no re-querying needed.
"""
import json
import logging

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)

GROUP_ID = "prana-audit-consumer"


class AuditConsumer:
    def __init__(self, settings: Settings, db_pool: asyncpg.Pool) -> None:
        self._pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.audit.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False,   # manual commit — commit only after successful DB write
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("AuditConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._write_audit(event)
                    await self._consumer.commit()
                except asyncpg.UniqueViolationError:
                    # Already written (duplicate delivery) — commit and move on
                    await self._consumer.commit()
                except Exception:
                    log.exception("AuditConsumer DB write failed event_type=%s", event.get("event_type"))
                    # Don't commit — message will be redelivered
        finally:
            await self._consumer.stop()

    async def _write_audit(self, event: dict) -> None:
        etype     = event["event_type"]
        tenant_id = event.get("tenant_id")
        doc_id    = event.get("document_id")
        actor_id  = event.get("actor_id")
        actor_type = event.get("actor_type", "SYSTEM")
        ip        = event.get("ip_address")
        occurred  = event.get("occurred_at")

        # Strip routing keys from metadata — store the full payload as context
        metadata = {k: v for k, v in event.items()
                    if k not in ("event_type", "event_id", "actor_id", "actor_type",
                                 "tenant_id", "document_id", "ip_address", "occurred_at")}

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_event
                  (event_type, actor_type, actor_id, tenant_id, document_id,
                   ip_address, event_metadata, occurred_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb,
                        COALESCE($8::timestamptz, NOW()))
                ON CONFLICT DO NOTHING
                """,
                etype, actor_type, actor_id, tenant_id, doc_id,
                ip, json.dumps(metadata), occurred,
            )
