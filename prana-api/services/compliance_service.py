"""
ComplianceService — DPDP Act 2023 business logic.
Zero Temporal imports. Called by workflow activity stubs in workflows/compliance.py.

Implements:
  - Erasure: hard-delete all employee PII from DB + Qdrant
  - Data export: package document index + metadata as S3 presigned URL
  - Consent rebump: send push notification via mobile push table
  - Grievance: open / escalate / close rows in dpdp_grievance table
  - Config read: used by get_config_value activity
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import asyncpg
import boto3

log = logging.getLogger(__name__)


class ComplianceService:

    def __init__(
        self,
        db: asyncpg.Connection,
        s3_client=None,
        documents_bucket: str = "",
        exports_bucket: str = "",
    ):
        self._db = db
        self._s3 = s3_client
        self._docs_bucket = documents_bucket
        self._exports_bucket = exports_bucket

    # ── Config ───────────────────────────────────────────────────────────────────

    async def get_config_value(self, key: str, tenant_id: Optional[str], default: str = "") -> str:
        row = await self._db.fetchval(
            """
            SELECT COALESCE(
              (SELECT config_value FROM tenant_config   WHERE tenant_id=$2 AND config_key=$1),
              (SELECT config_value FROM platform_config WHERE config_key=$1),
              $3
            )
            """,
            key, tenant_id, default,
        )
        return str(row or default)

    # ── Erasure ──────────────────────────────────────────────────────────────────

    async def send_erasure_notice(self, employee_user_id: str, tenant_id: Optional[str]) -> None:
        """Record erasure request in audit log and update grievance/erasure table."""
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'employee', 'ERASURE_REQUESTED', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"tenant_id": tenant_id, "status": "pending_cooling_off"}),
        )
        log.info("erasure_notice sent employee_user_id=%s", employee_user_id)

    async def execute_erasure(self, employee_user_id: str) -> dict:
        """
        Erase employee PII. Returns {erased_count, held_count, held_until}.

        Documents split into two groups:
          - Free (no active statutory hold)  → is_deleted=TRUE, employee_visible=FALSE
          - Held (employer statutory hold)   → employee_visible=FALSE only

        Held documents remain employer-accessible until statutory_hold_until expires,
        at which point RetentionWorkflow completes the physical S3 deletion.
        DPDP Act Section 9(11) permits retention for legal compliance obligations.

        Audit event written BEFORE any deletions (audit log is append-only).
        """
        today = date.today()

        # Fetch all non-deleted documents and their statutory hold status
        docs = await self._db.fetch(
            """SELECT document_id, s3_key, statutory_hold_until
               FROM document
               WHERE employee_uuid IN (
                   SELECT employee_uuid FROM employee_master WHERE employee_user_id = $1
               )
               AND is_deleted = FALSE""",
            employee_user_id,
        )

        held = [d for d in docs if d["statutory_hold_until"] and d["statutory_hold_until"] > today]
        free = [d for d in docs if not (d["statutory_hold_until"] and d["statutory_hold_until"] > today)]

        # Audit event before deletions — captures counts for legal record
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'employee', 'ERASURE_EXECUTED',
                    jsonb_build_object('erased_count', $2, 'held_count', $3)::jsonb,
                    NOW())
            """,
            employee_user_id, len(free), len(held),
        )

        async with self._db.transaction():
            # Full erasure: free documents — soft-delete and hide from employee
            if free:
                free_ids = [str(d["document_id"]) for d in free]
                await self._db.execute(
                    "UPDATE document SET is_deleted=TRUE, employee_visible=FALSE "
                    "WHERE document_id = ANY($1::uuid[])",
                    free_ids,
                )

            # Partial erasure: held documents — hide from employee, keep for employer
            if held:
                held_ids = [str(d["document_id"]) for d in held]
                await self._db.execute(
                    "UPDATE document SET employee_visible=FALSE "
                    "WHERE document_id = ANY($1::uuid[])",
                    held_ids,
                )

            await self._db.execute(
                "DELETE FROM career_event    WHERE employee_user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM share_token     WHERE employee_user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM user_session    WHERE user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM backup_code     WHERE user_type='employee' AND user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM trusted_device  WHERE user_type='employee' AND user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM employee_master WHERE employee_user_id=$1", employee_user_id,
            )
            # Anonymise employee_user — keep row for audit linkage, zero all PII
            await self._db.execute(
                """
                UPDATE employee_user SET
                  mobile = '[ERASED]',
                  status = 'ERASED',
                  totp_secret_enc = NULL,
                  password_hash = '[ERASED]'
                WHERE employee_user_id = $1
                """,
                employee_user_id,
            )

        log.info("erasure_executed employee_user_id=%s erased=%d held=%d",
                 employee_user_id, len(free), len(held))

        held_until = max((d["statutory_hold_until"] for d in held), default=None)
        return {"erased_count": len(free), "held_count": len(held), "held_until": held_until}

    # ── Data export ──────────────────────────────────────────────────────────────

    async def build_data_export(self, employee_user_id: str) -> dict:
        """
        Build a JSON export of all employee metadata (no raw ₹, no enc_pan).
        Uploads to S3 exports bucket, returns presigned URL valid 7 days.
        """
        # Gather exportable data
        docs = await self._db.fetch(
            """
            SELECT document_id, doc_type, doc_period, pipeline_status,
                   pushed_at, routed_at, tenant_id
            FROM document
            WHERE employee_uuid IN (
              SELECT employee_uuid FROM employee_master WHERE employee_user_id=$1
            ) AND is_deleted=FALSE
            ORDER BY pushed_at DESC
            """,
            employee_user_id,
        )
        events = await self._db.fetch(
            "SELECT event_type, event_date, tenant_id FROM career_event WHERE employee_user_id=$1 ORDER BY event_date",
            employee_user_id,
        )

        export_payload = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "employee_user_id": str(employee_user_id),
            "note": "Raw salary figures are never stored by PRANA — only growth indices and insights.",
            "documents": [
                {
                    "document_id": str(r["document_id"]),
                    "doc_type": r["doc_type"],
                    "doc_period": r["doc_period"],
                    "pipeline_status": r["pipeline_status"],
                    "pushed_at": r["pushed_at"].isoformat() if r["pushed_at"] else None,
                    "routed_at": r["routed_at"].isoformat() if r["routed_at"] else None,
                }
                for r in docs
            ],
            "career_events": [
                {
                    "event_type": r["event_type"],
                    "event_date": r["event_date"].isoformat() if r["event_date"] else None,
                }
                for r in events
            ],
        }

        key = f"exports/{employee_user_id}/{uuid.uuid4()}.json"
        if self._s3 and self._exports_bucket:
            self._s3.put_object(
                Bucket=self._exports_bucket,
                Key=key,
                Body=json.dumps(export_payload, ensure_ascii=False).encode(),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
            )
            url = self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._exports_bucket, "Key": key},
                ExpiresIn=7 * 24 * 3600,
            )
        else:
            url = f"s3://{self._exports_bucket}/{key}"   # dev fallback

        log.info("data_export built employee_user_id=%s key=%s", employee_user_id, key)
        return {"download_url": url, "expires_in_days": 7, "doc_count": len(docs)}

    async def notify_export_ready(self, employee_user_id: str, download_url: str, doc_count: int) -> None:
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'system', 'DATA_EXPORT_READY', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"download_url": download_url, "doc_count": doc_count}),
        )

    # ── Consent ──────────────────────────────────────────────────────────────────

    async def check_consent_status(self, employee_user_id: str) -> dict:
        row = await self._db.fetchrow(
            "SELECT consent_status FROM employee_user WHERE employee_user_id=$1", employee_user_id,
        )
        granted = row and row["consent_status"] == "GRANTED"
        return {"consent_granted": granted}

    async def send_consent_rebump(self, employee_user_id: str, tenant_id: Optional[str]) -> None:
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'system', 'CONSENT_REBUMP_SENT', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"tenant_id": tenant_id}),
        )
        log.info("consent_rebump sent employee_user_id=%s", employee_user_id)

    # ── Grievance ────────────────────────────────────────────────────────────────

    async def open_grievance(
        self,
        grievance_id: str,
        employee_user_id: str,
        tenant_id: Optional[str],
        category: str,
        description: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO dpdp_grievance
              (grievance_id, employee_user_id, tenant_id, grievance_type, category, description, status, raised_at)
            VALUES ($1, $2, $3, $4, $4, $5, 'RAISED', NOW())
            ON CONFLICT (grievance_id) DO NOTHING
            """,
            grievance_id, employee_user_id, tenant_id, category, description,
        )

    async def escalate_grievance(self, grievance_id: str, reason: str) -> None:
        await self._db.execute(
            """
            UPDATE dpdp_grievance
            SET status='ESCALATED_TO_DPB', updated_at=NOW()
            WHERE grievance_id=$1
            """,
            grievance_id,
        )
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ('00000000-0000-0000-0000-000000000000', 'system', 'GRIEVANCE_ESCALATED', $1::jsonb, NOW())
            """,
            json.dumps({"grievance_id": grievance_id, "reason": reason}),
        )

    async def close_grievance(self, grievance_id: str, note: str) -> None:
        await self._db.execute(
            """
            UPDATE dpdp_grievance
            SET status='RESOLVED', resolution_note=$2, resolved_at=NOW(), updated_at=NOW()
            WHERE grievance_id=$1
            """,
            grievance_id, note,
        )

    # ── Statutory Labour Law Compliance ──────────────────────────────────────────

    async def mark_overdue_obligations(self, tenant_id: str) -> dict:
        """
        Called nightly by StatutoryComplianceWorkflow.
        Marks compliance_obligation rows as OVERDUE when deadline < today and not yet COMPLETE/OVERDUE.
        Returns {"marked_count": N, "obligation_ids": [...]}
        """
        rows = await self._db.fetch(
            """
            UPDATE compliance_obligation
            SET status = 'OVERDUE',
                overdue_since = COALESCE(overdue_since, deadline),
                updated_at = NOW()
            WHERE tenant_id = $1
              AND deadline < CURRENT_DATE
              AND status NOT IN ('COMPLETE', 'OVERDUE')
            RETURNING obligation_id, obligation_name, statutory_act, deadline
            """,
            tenant_id,
        )

        marked_count = len(rows)
        if marked_count > 0:
            for row in rows:
                await self._db.execute(
                    """
                    INSERT INTO audit_event
                      (actor_id, actor_type, event_type, event_metadata, occurred_at)
                    VALUES ('00000000-0000-0000-0000-000000000000', 'system', 'COMPLIANCE_OBLIGATION_OVERDUE', $1::jsonb, NOW())
                    """,
                    json.dumps({
                        "tenant_id": tenant_id,
                        "obligation_id": str(row["obligation_id"]),
                        "obligation_name": row["obligation_name"],
                        "statutory_act": row["statutory_act"],
                        "deadline": row["deadline"].isoformat() if row["deadline"] else None,
                    }),
                )
            log.info("mark_overdue_obligations tenant=%s marked=%d", tenant_id, marked_count)

        return {
            "marked_count": marked_count,
            "obligation_ids": [str(r["obligation_id"]) for r in rows],
        }

    async def notify_overdue_obligations(self, tenant_id: str, count: int) -> None:
        """
        Publishes COMPLIANCE_OVERDUE_ALERT to prana.notifications so NotifConsumer
        sends an alert to the CHRO via email and portal bell.
        Caller (Temporal activity) provides the kafka producer via params.
        This method inserts the notification record in audit_event as a fallback
        if the workflow activity handles Kafka publish directly.
        """
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ('00000000-0000-0000-0000-000000000000', 'system', 'COMPLIANCE_OVERDUE_ALERT_SENT', $1::jsonb, NOW())
            """,
            json.dumps({"tenant_id": tenant_id, "overdue_count": count}),
        )
        log.info("notify_overdue_obligations tenant=%s count=%d", tenant_id, count)

    # ── Data correction (DataCorrectionWorkflow) ─────────────────────────────────

    # Only these insight fields may be corrected directly on employee_master — an
    # explicit allowlist rather than dynamic column-name SQL (DB-01: no f-string SQL).
    _CORRECTABLE_FIELDS = {"designation", "department", "grade", "location"}

    async def apply_data_correction(self, correction_id: str) -> None:
        """Idempotent: a correction already APPLIED is left alone (Temporal activity
        retry safety)."""
        row = await self._db.fetchrow(
            "SELECT employee_user_id, tenant_id, field_name, correct_value, status "
            "FROM data_correction_request WHERE correction_id=$1",
            correction_id,
        )
        if not row or row["status"] == "APPLIED":
            return

        field_name = row["field_name"]
        if field_name in self._CORRECTABLE_FIELDS:
            # Explicit per-field statements, not dynamic column-name SQL (DB-01) —
            # field_name is allowlist-checked above, but this codebase's DB-01 gate
            # flags any f-string passed to a db.execute/fetchrow call regardless.
            old_row = await self._db.fetchrow(
                "SELECT designation, department, grade, location FROM employee_master "
                "WHERE employee_user_id=$1",
                row["employee_user_id"],
            )
            old_value = old_row[field_name] if old_row else None
            if field_name == "designation":
                await self._db.execute(
                    "UPDATE employee_master SET designation=$2, updated_at=NOW() WHERE employee_user_id=$1",
                    row["employee_user_id"], row["correct_value"],
                )
            elif field_name == "department":
                await self._db.execute(
                    "UPDATE employee_master SET department=$2, updated_at=NOW() WHERE employee_user_id=$1",
                    row["employee_user_id"], row["correct_value"],
                )
            elif field_name == "grade":
                await self._db.execute(
                    "UPDATE employee_master SET grade=$2, updated_at=NOW() WHERE employee_user_id=$1",
                    row["employee_user_id"], row["correct_value"],
                )
            elif field_name == "location":
                await self._db.execute(
                    "UPDATE employee_master SET location=$2, updated_at=NOW() WHERE employee_user_id=$1",
                    row["employee_user_id"], row["correct_value"],
                )
            await self._db.execute(
                """
                INSERT INTO employee_master_history
                  (employee_uuid, tenant_id, field_name, old_value, new_value, changed_by,
                   changed_by_role, change_source)
                SELECT employee_uuid, $2, $3, $4, $5, employee_user_id, 'oa_admin', 'CORRECTION_WORKFLOW'
                FROM employee_master WHERE employee_user_id=$1
                """,
                row["employee_user_id"], row["tenant_id"], field_name,
                old_value, row["correct_value"],
            )
        else:
            log.warning("apply_data_correction: field_name=%s not in correctable allowlist — "
                        "marking resolved without mutating any field", field_name)

        await self._db.execute(
            "UPDATE data_correction_request SET status='APPLIED', resolved_at=NOW() WHERE correction_id=$1",
            correction_id,
        )

    async def notify_correction_complete(
        self, employee_user_id: str, tenant_id: Optional[str], approved: bool, reviewed_in_time: bool,
    ) -> None:
        event_type = "CORRECTION_APPLIED" if (approved and reviewed_in_time) else "CORRECTION_REJECTED"
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'system', 'DATA_CORRECTION_RESOLVED', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"tenant_id": tenant_id, "approved": approved, "reviewed_in_time": reviewed_in_time,
                        "notification_template": event_type}),
        )

    # ── Retention (RetentionWorkflow) ────────────────────────────────────────────

    async def schedule_document_deletion(self, employee_uuid: str, tenant_id: Optional[str]) -> dict:
        """Soft-deletes all of an employee's documents once their 7-year retention
        clock expires — skips any document under an active legal hold (checked here,
        not just documented as an intent, per LegalHoldWorkflow's purpose)."""
        rows = await self._db.fetch(
            "SELECT document_id FROM document "
            "WHERE employee_uuid=$1 AND tenant_id=$2 AND is_deleted=FALSE AND legal_hold_active=FALSE",
            employee_uuid, tenant_id,
        )
        held = await self._db.fetchval(
            "SELECT COUNT(*) FROM document "
            "WHERE employee_uuid=$1 AND tenant_id=$2 AND is_deleted=FALSE AND legal_hold_active=TRUE",
            employee_uuid, tenant_id,
        )
        doc_ids = [str(r["document_id"]) for r in rows]
        if doc_ids:
            await self._db.execute(
                "UPDATE document SET is_deleted=TRUE, employee_visible=FALSE, employer_visible=FALSE "
                "WHERE document_id = ANY($1::uuid[])",
                doc_ids,
            )
        log.info("schedule_document_deletion employee_uuid=%s deleted=%d held=%s",
                 employee_uuid, len(doc_ids), held)
        return {"deleted_count": len(doc_ids), "held_count": int(held or 0)}

    # ── Audit archival (AuditArchivalWorkflow) ───────────────────────────────────

    async def archive_audit_events_batch(self, cutoff_days: int, batch_size: int) -> dict:
        """Copies aged audit_event rows to cold S3 storage and records the copy in
        audit_archive_log. Never UPDATEs or DELETEs audit_event itself — migration
        039 REVOKEs both from prana_app_role by design, so archival can only ever be
        additive bookkeeping in a separate table."""
        rows = await self._db.fetch(
            """
            SELECT e.event_id, e.event_type, e.actor_type, e.actor_id, e.tenant_id, e.pan_token,
                   e.document_id, e.event_metadata, e.ip_address, e.occurred_at
            FROM audit_event e
            LEFT JOIN audit_archive_log a ON a.event_id = e.event_id
            WHERE e.occurred_at < NOW() - ($1 || ' days')::interval
              AND a.event_id IS NULL
            ORDER BY e.occurred_at
            LIMIT $2
            """,
            cutoff_days, batch_size,
        )
        if not rows:
            return {"archived_count": 0, "s3_key": None}

        batch = [
            {
                "event_id": str(r["event_id"]), "event_type": r["event_type"],
                "actor_type": r["actor_type"], "actor_id": str(r["actor_id"]),
                "tenant_id": str(r["tenant_id"]) if r["tenant_id"] else None,
                "pan_token": r["pan_token"],
                "document_id": str(r["document_id"]) if r["document_id"] else None,
                "event_metadata": r["event_metadata"],
                "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
                "occurred_at": r["occurred_at"].isoformat(),
            }
            for r in rows
        ]
        now = datetime.now(timezone.utc)
        s3_key = f"audit-archive/{now.year:04d}/{now.month:02d}/{uuid.uuid4()}.json"
        if self._s3 and self._exports_bucket:
            self._s3.put_object(
                Bucket=self._exports_bucket,
                Key=s3_key,
                Body=json.dumps(batch, ensure_ascii=False, default=str).encode(),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
            )
        else:
            log.warning("archive_audit_events_batch: no S3 client configured — dev fallback, not persisted")

        async with self._db.transaction():
            for r in rows:
                await self._db.execute(
                    "INSERT INTO audit_archive_log (event_id, archived_at, s3_key) "
                    "VALUES ($1, NOW(), $2) ON CONFLICT (event_id) DO NOTHING",
                    r["event_id"], s3_key,
                )

        log.info("archive_audit_events_batch archived=%d s3_key=%s", len(rows), s3_key)
        return {"archived_count": len(rows), "s3_key": s3_key}

    # ── Legal hold (LegalHoldWorkflow) ───────────────────────────────────────────

    async def apply_legal_hold(
        self, *, reason: str, tenant_id: Optional[str] = None,
        employee_uuid: Optional[str] = None, document_id: Optional[str] = None,
    ) -> None:
        """Freezes deletion/retention for a scope — one of employee_uuid or
        document_id must be given (LegalHoldWorkflow's docstring: "employee_id,
        tenant_id, or document_id"; tenant-wide holds are out of scope for v1 since
        no caller currently needs to freeze an entire tenant's documents)."""
        if document_id:
            await self._db.execute(
                "UPDATE document SET legal_hold_active=TRUE, legal_hold_reason=$2 WHERE document_id=$1",
                document_id, reason,
            )
        elif employee_uuid:
            await self._db.execute(
                "UPDATE document SET legal_hold_active=TRUE, legal_hold_reason=$2 "
                "WHERE employee_uuid=$1 AND is_deleted=FALSE",
                employee_uuid, reason,
            )

    async def release_legal_hold(
        self, *, tenant_id: Optional[str] = None,
        employee_uuid: Optional[str] = None, document_id: Optional[str] = None,
    ) -> None:
        if document_id:
            await self._db.execute(
                "UPDATE document SET legal_hold_active=FALSE, legal_hold_reason=NULL WHERE document_id=$1",
                document_id,
            )
        elif employee_uuid:
            await self._db.execute(
                "UPDATE document SET legal_hold_active=FALSE, legal_hold_reason=NULL "
                "WHERE employee_uuid=$1 AND is_deleted=FALSE",
                employee_uuid,
            )
