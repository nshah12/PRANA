"""
AuditConsumer — prana.audit.events

Writes every domain event to audit_event (immutable — no UPDATE/DELETE ever).
Runs independently so the HTTP handler never blocks on audit writes.

Subscribes to prana.audit.events which receives copies of:
  DOC_INGESTED, BATCH_UPLOADED, STAGE_CHANGED, DOC_ROUTED,
  EXCEPTION_RAISED, EXCEPTION_RESOLVED, EXCEPTION_DISMISSED,
  ELEVATION_APPROVED, ELEVATION_ENDED, ...

The event payload IS the audit metadata — no re-querying needed.

Commit strategy: micro-batch — commit every BATCH_SIZE messages or FLUSH_SECS
seconds (whichever comes first). This reduces Kafka round-trips from O(N) to
O(N/BATCH_SIZE) under high-ingest bursts, while keeping redelivery blast radius
bounded to at most BATCH_SIZE messages.
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterable, Iterable

import anyio.to_thread
import asyncpg
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.structs import OffsetAndMetadata

from config import Settings

log = logging.getLogger(__name__)

GROUP_ID  = "prana-audit-consumer"
BATCH_SIZE = 500
FLUSH_SECS = 5.0


class AuditConsumer:
    def __init__(self, settings: Settings, db_pool: asyncpg.Pool, immudb_service=None) -> None:
        self._pool = db_pool
        self._immudb = immudb_service
        self._consumer = AIOKafkaConsumer(
            "prana.audit.events",
            "prana.vault.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("AuditConsumer started")
        try:
            await self._run_loop(self._consumer)
        finally:
            await self._consumer.stop()

    async def _run_loop(self, messages) -> None:
        """
        Micro-batch commit loop. Extracted so unit tests can pass a plain list
        of messages without a live Kafka connection.
        """
        pending: dict[TopicPartition, OffsetAndMetadata] = {}
        last_flush = time.monotonic()

        async def _flush():
            if pending:
                await self._consumer.commit(offsets=pending)
                pending.clear()

        async def _iter():
            # Accept either an async iterable (live consumer) or a plain list (tests).
            if hasattr(messages, "__aiter__"):
                async for m in messages:
                    yield m
            else:
                for m in messages:
                    yield m

        async for msg in _iter():
            event = msg.value
            tp    = TopicPartition(msg.topic, msg.partition)
            next_offset = OffsetAndMetadata(msg.offset + 1, "")

            try:
                if event.get("event_type") == "DOC_ACCESSED":
                    await self._write_access_log(event)
                else:
                    await self._write_audit(event)
                pending[tp] = next_offset
            except asyncpg.UniqueViolationError:
                # Duplicate delivery — advance past it
                pending[tp] = next_offset
            except Exception:
                log.exception(
                    "AuditConsumer write failed event_type=%s doc=%s",
                    event.get("event_type"), event.get("document_id"),
                )
                # Flush good messages collected so far, then skip this one
                await _flush()
                pending[tp] = next_offset  # skip failed message

            now = time.monotonic()
            if len(pending) >= BATCH_SIZE or (now - last_flush) >= FLUSH_SECS:
                await _flush()
                last_flush = now

        # Final flush for any messages remaining below the batch threshold
        await _flush()

    async def _write_access_log(self, event: dict) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO document_access_log
                  (document_id, employee_user_id, employee_uuid, tenant_id,
                   actor_type, actor_id, access_type, access_channel,
                   ip_address, session_id, watermark_applied, accessed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        COALESCE($12::timestamptz, NOW()))
                ON CONFLICT DO NOTHING
                """,
                event.get("document_id"), event.get("employee_user_id"),
                event.get("employee_uuid"), event.get("tenant_id"),
                event.get("actor_type", "EMPLOYEE"), event.get("actor_id"),
                event.get("access_type"), event.get("access_channel"),
                event.get("ip_address"), event.get("session_id"),
                bool(event.get("watermark_applied", True)),
                event.get("occurred_at"),
            )

    async def _write_audit(self, event: dict) -> None:
        etype     = event["event_type"]
        tenant_id = event.get("tenant_id")
        doc_id    = event.get("document_id")
        actor_id  = event.get("actor_id") or "00000000-0000-0000-0000-000000000000"
        actor_type = event.get("actor_type", "SYSTEM")
        ip        = event.get("ip_address")
        occurred  = event.get("occurred_at")

        # Strip routing keys from metadata — store the full payload as context
        metadata = {k: v for k, v in event.items()
                    if k not in ("event_type", "event_id", "actor_id", "actor_type",
                                 "tenant_id", "document_id", "ip_address", "occurred_at")}

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_event
                  (event_type, actor_type, actor_id, tenant_id, document_id,
                   ip_address, event_metadata, occurred_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb,
                        COALESCE($8::timestamptz, NOW()))
                ON CONFLICT DO NOTHING
                RETURNING event_id
                """,
                etype, actor_type, actor_id, tenant_id, doc_id,
                ip, json.dumps(metadata), occurred,
            )

        # Dual-write to the tamper-evident Immudb ledger. Best-effort: Immudb is a
        # secondary verification store — its failure must never break the primary
        # audit_event write or stall the consumer. Skip on ON CONFLICT DO NOTHING
        # (row is None) since that event was already dual-written on first delivery.
        if self._immudb is not None and row is not None:
            event_id = str(row["event_id"])
            try:
                await anyio.to_thread.run_sync(
                    self._immudb.verified_set,
                    f"audit:{event_id}",
                    {
                        "event_id": event_id,
                        "event_type": etype,
                        "actor_type": actor_type,
                        "actor_id": actor_id,
                        "tenant_id": tenant_id,
                        "document_id": doc_id,
                        "ip_address": ip,
                        "event_metadata": metadata,
                        "occurred_at": occurred,
                    },
                )
            except Exception:
                log.exception(
                    "Immudb dual-write failed event_id=%s event_type=%s", event_id, etype,
                )
