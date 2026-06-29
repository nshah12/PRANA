"""
Vault service — employee-facing document access.
Every method is scoped to employee_user_id from JWT — never accepts it as a parameter.
Documents are AES-256-GCM encrypted in S3 — decrypted in-memory, never written to disk.

Access logging: every document access publishes DOC_ACCESSED to prana.vault.events.
AuditConsumer writes document_access_log asynchronously — zero latency on document serve.
"""
import io
import json
import logging
from typing import Optional

import asyncpg
from services.encryption_service import KMSService, aes_decrypt

log = logging.getLogger(__name__)

TOPIC_VAULT = "prana.vault.events"


class VaultService:

    def __init__(
        self,
        db: asyncpg.Connection,
        kms: KMSService,
        s3_client,
        documents_bucket: str,
        kafka_producer=None,
    ):
        self._db = db
        self._kms = kms
        self._s3 = s3_client
        self._bucket = documents_bucket
        self._kafka = kafka_producer

    # ── Document listing ──────────────────────────────────────────────────────

    async def list_documents(
        self,
        employee_user_id: str,
        *,
        doc_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["d.is_deleted = FALSE"]
        params: list = [employee_user_id]
        i = 2

        # Scope to authenticated employee via employee_master join
        base = """
            SELECT d.document_id, d.doc_type, d.doc_period, d.pipeline_status,
                   d.tenant_id, t.tenant_name, d.pushed_at, d.routed_at,
                   d.is_self_upload, d.original_filename,
                   em.designation, em.department, em.doj, em.dol
            FROM document d
            JOIN employee_master em ON em.employee_uuid = d.employee_uuid
            JOIN tenant t ON t.tenant_id = d.tenant_id
            JOIN employee_user eu ON eu.employee_user_id = em.employee_user_id
            WHERE eu.employee_user_id = $1
        """

        if doc_type:
            conditions.append(f"d.doc_type = ${i}"); params.append(doc_type); i += 1
        if tenant_id:
            conditions.append(f"d.tenant_id = ${i}"); params.append(tenant_id); i += 1

        conditions.append("d.pipeline_status IN ('ROUTED','QUEUED','ENCRYPTING','SCANNING','EXTRACTING','RESOLVING')")
        where = " AND ".join(conditions)

        rows = await self._db.fetch(
            base + " AND " + where + " ORDER BY d.pushed_at DESC LIMIT $" + str(i) + " OFFSET $" + str(i + 1),
            *params, limit, offset,
        )
        return [
            {
                "document_id": str(r["document_id"]),
                "doc_type": r["doc_type"],
                "doc_period": r["doc_period"],
                "pipeline_status": r["pipeline_status"],
                "tenant_id": str(r["tenant_id"]),
                "tenant_name": r["tenant_name"],
                "pushed_at": r["pushed_at"].isoformat() if r["pushed_at"] else None,
                "routed_at": r["routed_at"].isoformat() if r["routed_at"] else None,
                "is_self_upload": r["is_self_upload"],
                "original_filename": r["original_filename"],
                "designation": r["designation"],
                "department": r["department"],
                "doj": r["doj"].isoformat() if r["doj"] else None,
                "dol": r["dol"].isoformat() if r["dol"] else None,
            }
            for r in rows
        ]

    # ── Document fetch (decrypt + serve) ──────────────────────────────────────

    async def get_document_bytes(
        self,
        document_id: str,
        employee_user_id: str,
        actor_ip: str,
        session_id: str,
        access_type: str = "VIEW",
    ) -> tuple[bytes, str]:
        """
        Decrypts document in-memory. Returns (plaintext_bytes, doc_type).
        Writes document_access_log. Never writes decrypted bytes to disk.
        """
        row = await self._db.fetchrow(
            """
            SELECT d.document_id, d.doc_type, d.s3_key, d.s3_bucket,
                   em.employee_uuid, em.tenant_id, em.enc_dek,
                   eu.employee_user_id,
                   t.kek_arn
            FROM document d
            JOIN employee_master em ON em.employee_uuid = d.employee_uuid
            JOIN employee_user eu   ON eu.employee_user_id = em.employee_user_id
            JOIN tenant t           ON t.tenant_id = em.tenant_id
            WHERE d.document_id = $1
              AND eu.employee_user_id = $2
              AND d.pipeline_status = 'ROUTED'
              AND d.is_deleted = FALSE
            """,
            document_id, employee_user_id,
        )
        if not row:
            raise PermissionError("DOCUMENT_NOT_FOUND")

        # Unwrap DEK from KMS
        dek = self._kms.unwrap_dek(row["enc_dek"], row["kek_arn"])

        # Fetch and decrypt from S3/MinIO
        raw = self._s3.get_object(row["s3_bucket"], row["s3_key"])
        nonce, ct = raw[:12], raw[12:]

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plaintext = AESGCM(dek).decrypt(nonce, ct, None)
        del dek  # clear DEK immediately

        # For share-link access, session_id is a non-UUID label — pass NULL to FK column
        import uuid as _uuid
        try:
            parsed_session_id = str(_uuid.UUID(session_id))
        except (ValueError, AttributeError):
            parsed_session_id = None

        # Publish access event — AuditConsumer writes document_access_log async
        await self._log_access(
            document_id=document_id,
            employee_user_id=employee_user_id,
            employee_uuid=str(row["employee_uuid"]),
            tenant_id=str(row["tenant_id"]),
            actor_type="EMPLOYEE" if parsed_session_id else "THIRD_PARTY",
            actor_id=employee_user_id,
            access_type=access_type,
            access_channel="MOBILE",
            ip_address=actor_ip,
            session_id=parsed_session_id,
        )

        return plaintext, row["doc_type"]

    # ── Career timeline ───────────────────────────────────────────────────────

    async def get_timeline(self, employee_user_id: str) -> list[dict]:
        """
        Returns career events across ALL employers, ordered chronologically.
        insight_text included — no raw ₹ or PAN in this table.
        """
        rows = await self._db.fetch(
            """
            SELECT ce.career_event_id, ce.event_type, ce.event_date,
                   ce.event_title, ce.designation, ce.grade,
                   ce.verified, ce.insight_text, ce.tenant_id,
                   t.tenant_name
            FROM career_event ce
            LEFT JOIN tenant t ON t.tenant_id = ce.tenant_id
            WHERE ce.employee_user_id = $1
            ORDER BY ce.event_date DESC
            """,
            employee_user_id,
        )
        return [
            {
                "career_event_id": str(r["career_event_id"]),
                "event_type": r["event_type"],
                "event_date": r["event_date"].isoformat() if r["event_date"] else None,
                "event_title": r["event_title"],
                "designation": r["designation"],
                "grade": r["grade"],
                "verified": r["verified"],
                "insight_text": r["insight_text"],
                "tenant_id": str(r["tenant_id"]) if r["tenant_id"] else None,
                "tenant_name": r["tenant_name"],
            }
            for r in rows
        ]

    # ── Vault health ──────────────────────────────────────────────────────────

    async def get_health(self, employee_user_id: str) -> Optional[dict]:
        row = await self._db.fetchrow(
            """
            SELECT vhs.overall_score, vhs.employment_proof_score,
                   vhs.salary_slip_score, vhs.form16_score,
                   vhs.gap_count, vhs.gap_detail, vhs.computed_at
            FROM vault_health_score vhs
            JOIN employee_user eu ON eu.pan_token = vhs.pan_token
            WHERE eu.employee_user_id = $1
            """,
            employee_user_id,
        )
        if not row:
            return None
        return {
            "overall_score": int(row["overall_score"]) if row["overall_score"] is not None else None,
            "employment_proof_score": int(row["employment_proof_score"]) if row["employment_proof_score"] is not None else None,
            "salary_slip_score": int(row["salary_slip_score"]) if row["salary_slip_score"] is not None else None,
            "form16_score": int(row["form16_score"]) if row["form16_score"] is not None else None,
            "gap_count": int(row["gap_count"]) if row["gap_count"] is not None else 0,
            "gap_detail": row["gap_detail"] if isinstance(row["gap_detail"], list) else [],
            "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
        }

    # ── Employer list ─────────────────────────────────────────────────────────

    async def get_employers(self, employee_user_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT DISTINCT t.tenant_id, t.tenant_name, t.domain,
                   em.doj, em.dol, em.designation, em.status AS employment_status
            FROM employee_master em
            JOIN tenant t ON t.tenant_id = em.tenant_id
            WHERE em.employee_user_id = $1
            ORDER BY em.doj DESC
            """,
            employee_user_id,
        )
        return [
            {
                "tenant_id": str(r["tenant_id"]),
                "tenant_name": r["tenant_name"],
                "domain": r["domain"],
                "doj": r["doj"].isoformat() if r["doj"] else None,
                "dol": r["dol"].isoformat() if r["dol"] else None,
                "designation": r["designation"],
                "employment_status": r["employment_status"],
            }
            for r in rows
        ]

    # ── Document request ──────────────────────────────────────────────────────

    async def request_document(
        self,
        employee_user_id: str,
        tenant_id: str,
        doc_type: str,
        period: Optional[str],
        note: Optional[str],
    ) -> str:
        pan_token = await self._db.fetchval(
            "SELECT pan_token FROM employee_user WHERE employee_user_id=$1", employee_user_id
        )
        # Verify employment relationship
        active = await self._db.fetchval(
            "SELECT 1 FROM employee_master WHERE employee_user_id=$1 AND tenant_id=$2",
            employee_user_id, tenant_id,
        )
        if not active:
            raise PermissionError("NOT_EMPLOYED_HERE")

        doc_request_id = await self._db.fetchval(
            """
            INSERT INTO document_request (pan_token, tenant_id, doc_type, period, note)
            VALUES ($1,$2,$3,$4,$5)
            RETURNING doc_request_id
            """,
            pan_token, tenant_id, doc_type, period, note,
        )
        return str(doc_request_id)

    async def list_requests(self, employee_user_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT dr.doc_request_id, dr.doc_type, dr.period, dr.status,
                   dr.requested_at, dr.fulfilled_at, t.tenant_name
            FROM document_request dr
            JOIN employee_user eu ON eu.pan_token = dr.pan_token
            JOIN tenant t ON t.tenant_id = dr.tenant_id
            WHERE eu.employee_user_id = $1
            ORDER BY dr.requested_at DESC
            """,
            employee_user_id,
        )
        return [
            {
                "doc_request_id": str(r["doc_request_id"]),
                "doc_type": r["doc_type"],
                "period": r["period"],
                "status": r["status"],
                "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
                "fulfilled_at": r["fulfilled_at"].isoformat() if r["fulfilled_at"] else None,
                "tenant_name": r["tenant_name"],
            }
            for r in rows
        ]

    # ── Access log ────────────────────────────────────────────────────────────

    async def _log_access(
        self, *, document_id, employee_user_id, employee_uuid,
        tenant_id, actor_type, actor_id, access_type, access_channel,
        ip_address, session_id,
    ) -> None:
        """
        Publish DOC_ACCESSED to prana.vault.events.
        AuditConsumer writes document_access_log asynchronously — no DB write here.
        Falls back to direct DB write if Kafka is unavailable (dev / Kafka-down scenarios).
        """
        event = {
            "event_type":        "DOC_ACCESSED",
            "document_id":       document_id,
            "employee_user_id":  employee_user_id,
            "employee_uuid":     employee_uuid,
            "tenant_id":         tenant_id,
            "actor_type":        actor_type,
            "actor_id":          actor_id,
            "access_type":       access_type,
            "access_channel":    access_channel,
            "ip_address":        ip_address,
            "session_id":        session_id,
            "watermark_applied": True,
        }

        if self._kafka:
            try:
                await self._kafka.doc_accessed(event)
                return
            except Exception:
                log.exception("Kafka unavailable — falling back to direct access_log write doc=%s", document_id)

        # Fallback: synchronous DB write (dev mode / Kafka down)
        await self._db.execute(
            """
            INSERT INTO document_access_log
              (document_id, employee_user_id, employee_uuid, tenant_id,
               actor_type, actor_id, access_type, access_channel,
               ip_address, session_id, watermark_applied, accessed_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::inet,$10,TRUE,NOW())
            """,
            document_id, employee_user_id, employee_uuid, tenant_id,
            actor_type, actor_id, access_type, access_channel, ip_address, session_id,
        )
