"""
AuditIntegrityService — re-verifies recent audit_event rows against their
Immudb dual-write to catch tampering applied directly against YugabyteDB.

Immudb's verified_get() can prove a stored value hasn't changed since it was
written, but only if something actually calls it. This service is that
"something" — called on a schedule by AuditIntegrityVerificationWorkflow
(workflows/audit_integrity.py, Pattern 3). Zero Temporal imports here.

See KAFKA_REDIS_ARCHITECTURE.md §8 and prana-db/migrations/039_audit_role_revoke.sql.
"""
import json
import logging

import anyio.to_thread

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 500


class AuditIntegrityService:

    def __init__(self, db, immudb_service, kafka=None):
        self._db = db
        self._immudb = immudb_service
        self._kafka = kafka

    async def verify_recent(self, limit: int = DEFAULT_LIMIT) -> dict:
        """
        Re-checks the most recent `limit` audit_event rows against Immudb.
        Returns counts + offending event_ids. Publishes a security_event
        (mismatched/unverified only — not missing) so CISO/security ops
        actually gets notified, not just a silent log line.
        """
        rows = await self._db.fetch(
            """
            SELECT event_id, event_type, actor_type, actor_id, tenant_id,
                   document_id, event_metadata, occurred_at
            FROM audit_event
            ORDER BY occurred_at DESC
            LIMIT $1
            """,
            limit,
        )

        checked = 0
        mismatched: list[str] = []
        missing: list[str] = []
        unverified: list[str] = []

        for row in rows:
            checked += 1
            event_id = str(row["event_id"])
            try:
                stored = await anyio.to_thread.run_sync(
                    self._immudb.verified_get, f"audit:{event_id}"
                )
            except Exception:
                log.exception("Immudb verified_get failed event_id=%s", event_id)
                unverified.append(event_id)
                continue

            if stored is None:
                missing.append(event_id)
                continue
            if not stored.get("verified", False):
                # Immudb's own cryptographic proof failed — this is the alarming case.
                unverified.append(event_id)
                continue
            if not self._matches(row, stored["value"]):
                mismatched.append(event_id)

        if mismatched or unverified:
            await self._alert(checked, mismatched, unverified)

        return {
            "checked": checked,
            "mismatched": mismatched,
            "missing": missing,
            "unverified": unverified,
        }

    @staticmethod
    def _matches(row, value: dict) -> bool:
        """
        Compares the current YugabyteDB row against what was dual-written to
        Immudb at insert time. occurred_at/ip_address are intentionally NOT
        compared: Immudb stores whatever the raw Kafka event contained, which
        is None when the producer didn't set it — the DB's own server-generated
        NOW()/NULL legitimately differs in that case, that's not tampering.
        """
        if row["event_type"] != value.get("event_type"):
            return False
        if row["actor_type"] != value.get("actor_type"):
            return False
        if str(row["actor_id"]) != str(value.get("actor_id")):
            return False
        if str(row["tenant_id"] or "") != str(value.get("tenant_id") or ""):
            return False
        if str(row["document_id"] or "") != str(value.get("document_id") or ""):
            return False

        db_metadata = row["event_metadata"]
        if isinstance(db_metadata, str):
            db_metadata = json.loads(db_metadata) if db_metadata else {}
        if (db_metadata or {}) != (value.get("event_metadata") or {}):
            return False

        return True

    async def _alert(self, checked: int, mismatched: list[str], unverified: list[str]) -> None:
        if not self._kafka:
            return
        await self._kafka.security_event({
            "event_type": "AUDIT_INTEGRITY_MISMATCH",
            "actor_type": "SYSTEM",
            "checked_count": checked,
            "mismatched_count": len(mismatched),
            "mismatched_ids": mismatched[:20],
            "unverified_count": len(unverified),
            "unverified_ids": unverified[:20],
        })
