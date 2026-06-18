"""
C-Share (Controlled Share) — employee grants a third party time-limited document access.
Token is an opaque UUID stored in share_token table.
OTP-gated shares require recipient to verify a 6-digit code before document is served.
Access events are written to document_access_log.
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg


def _generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


class ShareService:

    def __init__(self, db: asyncpg.Connection, redis, settings):
        self._db = db
        self._redis = redis
        self._settings = settings

    # ── Create share ──────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        employee_user_id: str,
        document_ids: list[str],
        expires_hours: int = 72,
        max_views: Optional[int] = 3,
        recipient_label: Optional[str] = None,
        otp_required: bool = False,
        recipient_email: Optional[str] = None,
    ) -> dict:
        if expires_hours < 1 or expires_hours > 720:   # 1h–30d
            raise ValueError("INVALID_EXPIRY")
        if not document_ids:
            raise ValueError("NO_DOCUMENTS")
        if len(document_ids) > 10:
            raise ValueError("TOO_MANY_DOCUMENTS")

        # Verify all docs belong to this employee and are ROUTED
        rows = await self._db.fetch(
            """
            SELECT d.document_id
            FROM document d
            JOIN employee_master em ON em.employee_uuid = d.employee_uuid
            WHERE em.employee_user_id = $1
              AND d.pipeline_status = 'ROUTED'
              AND d.is_deleted = FALSE
              AND d.document_id = ANY($2::uuid[])
            """,
            employee_user_id, document_ids,
        )
        if len(rows) != len(document_ids):
            raise PermissionError("DOCUMENT_NOT_FOUND_OR_NOT_READY")

        share_token = str(uuid.uuid4())
        expires_at  = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        otp_hash: Optional[str] = None
        otp_plain: Optional[str] = None
        if otp_required:
            otp_plain = _generate_otp()
            import hashlib
            otp_hash = hashlib.sha256(otp_plain.encode()).hexdigest()

        token_hash = _hash_token(share_token)
        recipient_identifier = recipient_email or "unspecified"
        # watermark_text is repurposed to store otp_hash when otp_required=True
        # (avoids schema migration; schema change tracked in TODO for migration 002)
        wm_text = otp_hash if otp_required else (recipient_label or recipient_identifier)

        async with self._db.transaction():
            share_id = await self._db.fetchval(
                """
                INSERT INTO share_token
                  (token_hash, pan_token, employee_user_id, document_ids,
                   recipient_identifier, access_type, expires_at,
                   usage_limit, otp_required, watermark_text, created_at)
                SELECT $1,
                       eu.pan_token,
                       $2::uuid,
                       $3::uuid[],
                       $4,
                       'VIEW_ONLY',
                       $5,
                       $6,
                       $7,
                       $8,
                       NOW()
                FROM employee_user eu
                WHERE eu.employee_user_id = $2
                RETURNING token_id
                """,
                token_hash, employee_user_id, document_ids,
                recipient_identifier, expires_at,
                max_views, otp_required, wm_text,
            )

        result: dict = {
            "share_id": str(share_id),
            "share_token": share_token,
            "expires_at": expires_at.isoformat(),
            "otp_required": otp_required,
        }
        if otp_plain:
            result["otp"] = otp_plain   # returned once; never stored plaintext
        return result

    # ── Validate share (called by public share_access router) ─────────────────

    async def validate_token(self, token: str) -> dict:
        token_hash = _hash_token(token)
        row = await self._db.fetchrow(
            """
            SELECT token_id, employee_user_id, document_ids, expires_at,
                   usage_limit, usage_count, otp_required, status
            FROM share_token
            WHERE token_hash = $1
            """,
            token_hash,
        )
        if not row:
            raise PermissionError("INVALID_TOKEN")
        if row["status"] == "REVOKED":
            raise PermissionError("TOKEN_REVOKED")
        if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise PermissionError("TOKEN_EXPIRED")
        if row["usage_limit"] and row["usage_count"] >= row["usage_limit"]:
            raise PermissionError("VIEW_LIMIT_REACHED")
        return {
            "share_id": row["token_id"],
            "employee_user_id": row["employee_user_id"],
            "document_ids": row["document_ids"],
            "expires_at": row["expires_at"],
            "max_views": row["usage_limit"],
            "views_used": row["usage_count"],
            "otp_required": row["otp_required"],
        }

    async def verify_otp(self, token: str, otp: str) -> bool:
        import hashlib
        # OTP hash stored in watermark_text column (repurposed for OTP storage)
        # In a production schema, add otp_hash column; for now use watermark_text
        token_hash = _hash_token(token)
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        stored = await self._db.fetchval(
            "SELECT watermark_text FROM share_token WHERE token_hash=$1 AND otp_required=TRUE",
            token_hash,
        )
        return stored == otp_hash

    async def increment_views(self, token: str) -> None:
        token_hash = _hash_token(token)
        await self._db.execute(
            "UPDATE share_token SET usage_count = usage_count + 1 WHERE token_hash = $1",
            token_hash,
        )

    # ── List employee's active shares ─────────────────────────────────────────

    async def list_shares(self, employee_user_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT token_id AS share_id, document_ids, expires_at,
                   usage_limit AS max_views, usage_count AS views_used,
                   recipient_identifier AS recipient_label, otp_required,
                   status, created_at
            FROM share_token
            WHERE employee_user_id = $1
            ORDER BY created_at DESC
            """,
            employee_user_id,
        )
        return [dict(r) for r in rows]

    # ── Revoke ────────────────────────────────────────────────────────────────

    async def revoke(self, share_id: str, employee_user_id: str) -> None:
        result = await self._db.execute(
            "UPDATE share_token SET status='REVOKED', revoked_at=NOW() "
            "WHERE token_id=$1 AND employee_user_id=$2 AND status='ACTIVE'",
            share_id, employee_user_id,
        )
        if result == "UPDATE 0":
            raise PermissionError("NOT_FOUND")
