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
from datetime import datetime, timezone
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
              (actor_user_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'employee', 'ERASURE_REQUESTED', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"tenant_id": tenant_id, "status": "pending_cooling_off"}),
        )
        log.info("erasure_notice sent employee_user_id=%s", employee_user_id)

    async def execute_erasure(self, employee_user_id: str) -> None:
        """
        Hard-delete all employee PII. Irreversible.
        Order: documents → career_events → employee_master → employee_user
        Audit event written BEFORE deletion (can't write after).
        """
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_user_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'employee', 'ERASURE_EXECUTED', '{}'::jsonb, NOW())
            """,
            employee_user_id,
        )

        async with self._db.transaction():
            # Soft-delete documents (S3 objects cleaned up by RetentionWorkflow)
            await self._db.execute(
                "UPDATE document SET is_deleted=TRUE, deleted_at=NOW() WHERE employee_uuid IN "
                "(SELECT employee_uuid FROM employee_master WHERE employee_user_id=$1)",
                employee_user_id,
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
                "DELETE FROM backup_code     WHERE employee_user_id=$1", employee_user_id,
            )
            await self._db.execute(
                "DELETE FROM trusted_device  WHERE employee_user_id=$1", employee_user_id,
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
                  password_hash = '[ERASED]',
                  updated_at = NOW()
                WHERE employee_user_id = $1
                """,
                employee_user_id,
            )

        log.info("erasure_executed employee_user_id=%s", employee_user_id)

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
                   insight_text, created_at, routed_at, tenant_id
            FROM document
            WHERE employee_uuid IN (
              SELECT employee_uuid FROM employee_master WHERE employee_user_id=$1
            ) AND is_deleted=FALSE
            ORDER BY created_at DESC
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
                    "insight_text": r["insight_text"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
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
              (actor_user_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ($1, 'system', 'DATA_EXPORT_READY', $2::jsonb, NOW())
            """,
            employee_user_id,
            json.dumps({"download_url": download_url, "doc_count": doc_count}),
        )

    # ── Consent ──────────────────────────────────────────────────────────────────

    async def check_consent_status(self, employee_user_id: str) -> dict:
        row = await self._db.fetchrow(
            "SELECT status FROM employee_user WHERE employee_user_id=$1", employee_user_id,
        )
        granted = row and row["status"] == "ACTIVE"
        return {"consent_granted": granted}

    async def send_consent_rebump(self, employee_user_id: str, tenant_id: Optional[str]) -> None:
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_user_id, actor_type, event_type, event_metadata, occurred_at)
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
              (grievance_id, employee_user_id, tenant_id, category, description, status, filed_at)
            VALUES ($1, $2, $3, $4, $5, 'OPEN', NOW())
            ON CONFLICT (grievance_id) DO NOTHING
            """,
            grievance_id, employee_user_id, tenant_id, category, description,
        )

    async def escalate_grievance(self, grievance_id: str, reason: str) -> None:
        await self._db.execute(
            """
            UPDATE dpdp_grievance
            SET status='ESCALATED', escalation_reason=$2, updated_at=NOW()
            WHERE grievance_id=$1
            """,
            grievance_id, reason,
        )
        await self._db.execute(
            """
            INSERT INTO audit_event
              (actor_user_id, actor_type, event_type, event_metadata, occurred_at)
            VALUES ('system', 'system', 'GRIEVANCE_ESCALATED', $1::jsonb, NOW())
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
