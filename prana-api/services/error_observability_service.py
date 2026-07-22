"""
ErrorObservabilityService — the 4th track of PRANA's incident system.

Captures caught/uncaught application exceptions (HTTP handlers, Kafka
consumers, Temporal activities) that previously had zero durable trace
anywhere — see prana-docs/ERROR_OBSERVABILITY_DESIGN.md for the full design
and rationale.

Deduplicates by fingerprint (exception type + raise-site location + a
normalized message) so a recurring bug is one row with a growing
occurrence_count, not thousands of near-identical rows.

Privacy (§6 of the design doc, non-negotiable): only exception_type,
str(exc), and the STANDARD traceback.format_exc() text are ever captured —
never local variable values (a realistic PAN/salary leak vector), and
message/traceback text is regex-scrubbed for PAN/JWT/email/mobile-shaped
strings before being written anywhere.

Zero Temporal imports — called directly, from the HTTP handler, the Kafka
consumer helper, and (via an activity interceptor) Temporal activities alike.
"""
import hashlib
import re
import traceback
import uuid as _uuid
from typing import Any, Optional

# ── PII scrubbing ────────────────────────────────────────────────────────────

_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_MOBILE_RE = re.compile(r"\+91\d{10}\b")
_MESSAGE_MAX_LEN = 2000

# Normalization for fingerprinting only — collapses variable data (UUIDs,
# digit runs, quoted strings) so the SAME bug with DIFFERENT input data still
# gets the SAME fingerprint. Applied to a throwaway copy, never persisted.
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_DIGITS_RE = re.compile(r"\d+")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


class ErrorObservabilityService:

    def __init__(self, db) -> None:
        self._db = db

    # ── Capture ──────────────────────────────────────────────────────────────

    async def record(
        self,
        *,
        exc: Exception,
        source: str,
        source_detail: Optional[str] = None,
        request_id: Optional[str] = None,
        event_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> str:
        fingerprint = self._fingerprint(exc)
        message = self._scrub(str(exc))
        tb = self._scrub("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

        existing = await self._db.fetchrow(
            "SELECT error_id, occurrence_count FROM error_event "
            "WHERE fingerprint = $1 AND status IN ('NEW', 'ACKNOWLEDGED')",
            fingerprint,
        )

        if existing:
            error_id = str(existing["error_id"])
            await self._db.execute(
                """
                UPDATE error_event
                   SET occurrence_count = occurrence_count + 1,
                       last_seen_at = NOW()
                 WHERE error_id = $1
                """,
                error_id,
            )
            return error_id

        error_id = str(_uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO error_event
              (error_id, fingerprint, exception_type, message, traceback,
               source, source_detail, request_id, event_id, tenant_id,
               actor_type, actor_id, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'NEW')
            """,
            error_id, fingerprint, type(exc).__name__, message, tb,
            source, source_detail, request_id, event_id, tenant_id,
            actor_type, actor_id,
        )
        return error_id

    def _fingerprint(self, exc: Exception) -> str:
        tb_frames = traceback.extract_tb(exc.__traceback__)
        top_frame = tb_frames[-1] if tb_frames else None
        location = f"{top_frame.filename}:{top_frame.lineno}" if top_frame else "unknown"
        normalized_message = self._normalize_for_fingerprint(str(exc))
        raw = f"{type(exc).__name__}:{location}:{normalized_message}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _normalize_for_fingerprint(message: str) -> str:
        message = _UUID_RE.sub("<uuid>", message)
        message = _QUOTED_RE.sub("<str>", message)
        message = _DIGITS_RE.sub("<n>", message)
        return message

    @staticmethod
    def _scrub(text: str) -> str:
        if not text:
            return text
        text = _JWT_RE.sub("[REDACTED]", text)
        text = _PAN_RE.sub("[REDACTED]", text)
        text = _EMAIL_RE.sub("[REDACTED]", text)
        text = _MOBILE_RE.sub("[REDACTED]", text)
        return text[:_MESSAGE_MAX_LEN]

    # ── Triage / lifecycle ───────────────────────────────────────────────────

    async def list_errors(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        include_platform_errors: bool = False,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1
        if tenant_id is not None:
            if include_platform_errors:
                conditions.append(f"(tenant_id = ${idx} OR tenant_id IS NULL)")
            else:
                conditions.append(f"tenant_id = ${idx}")
            params.append(tenant_id)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        rows = await self._db.fetch(
            f"""
            SELECT error_id, fingerprint, exception_type, source, source_detail,
                   tenant_id, occurrence_count, first_seen_at, last_seen_at,
                   status, linked_incident_id
              FROM error_event
             {where}
             ORDER BY last_seen_at DESC
             LIMIT ${idx}
            """,
            *params,
        )
        return [
            {
                "error_id":     str(r["error_id"]),
                "fingerprint":  r["fingerprint"],
                "exception_type": r["exception_type"],
                "source":       r["source"],
                "source_detail": r["source_detail"],
                "tenant_id":    str(r["tenant_id"]) if r["tenant_id"] else None,
                "occurrence_count": r["occurrence_count"],
                "first_seen_at": r["first_seen_at"].isoformat() if r["first_seen_at"] else None,
                "last_seen_at":  r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
                "status":       r["status"],
                "linked_incident_id": str(r["linked_incident_id"]) if r["linked_incident_id"] else None,
            }
            for r in rows
        ]

    async def acknowledge(self, *, error_id: str) -> None:
        row = await self._db.fetchrow("SELECT error_id FROM error_event WHERE error_id = $1", error_id)
        if not row:
            raise ValueError(f"error_event not found: {error_id}")
        await self._db.execute(
            "UPDATE error_event SET status = 'ACKNOWLEDGED' WHERE error_id = $1", error_id,
        )

    async def ignore(self, *, error_id: str) -> None:
        row = await self._db.fetchrow("SELECT error_id FROM error_event WHERE error_id = $1", error_id)
        if not row:
            raise ValueError(f"error_event not found: {error_id}")
        await self._db.execute(
            "UPDATE error_event SET status = 'IGNORED' WHERE error_id = $1", error_id,
        )

    async def resolve(self, *, error_id: str, resolved_by: str, resolution_note: str) -> None:
        if not resolution_note or not resolution_note.strip():
            raise ValueError("resolution_note is required")
        row = await self._db.fetchrow("SELECT error_id FROM error_event WHERE error_id = $1", error_id)
        if not row:
            raise ValueError(f"error_event not found: {error_id}")
        await self._db.execute(
            """
            UPDATE error_event
               SET status = 'RESOLVED', resolved_by = $1, resolved_at = NOW(), resolution_note = $2
             WHERE error_id = $3
            """,
            resolved_by, resolution_note, error_id,
        )

    async def promote_to_incident(self, *, error_id: str, severity: str) -> str:
        """Create a real incident for this error and link it. Reuses the SAME
        IncidentService/incident table as the business-event track — this
        design deliberately doesn't invent a second incident lifecycle."""
        row = await self._db.fetchrow(
            "SELECT error_id, exception_type, source_detail, tenant_id FROM error_event WHERE error_id = $1",
            error_id,
        )
        if not row:
            raise ValueError(f"error_event not found: {error_id}")

        from services.incident_service import IncidentService
        isvc = IncidentService(self._db)
        incident_id = await isvc.create_incident(
            incident_type="APPLICATION_ERROR",
            severity=severity,
            title=f"{row['exception_type']} in {row['source_detail']}",
            tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
            source_table="error_event",
            source_id=error_id,
        )
        await self._db.execute(
            "UPDATE error_event SET linked_incident_id = $1 WHERE error_id = $2",
            incident_id, error_id,
        )
        return incident_id
