"""
OA user lifecycle — OA-Admin operations.
Min-1-OA-Admin constraint enforced here before every demotion/deactivation.
"""
import uuid
import secrets
from typing import Optional

import asyncpg

from services.encryption_service import hash_password


class OAUserService:

    def __init__(self, db: asyncpg.Connection):
        self._db = db

    async def create(
        self,
        *,
        tenant_id: str,
        email: str,
        role: str,
        created_by: str,
    ) -> dict:
        """Create OA user with temp password (force_reset=TRUE)."""
        # Validate email matches tenant domain
        tenant = await self._db.fetchrow("SELECT domain FROM tenant WHERE tenant_id=$1", tenant_id)
        if not tenant:
            raise ValueError("TENANT_NOT_FOUND")
        if not email.endswith(f"@{tenant['domain']}"):
            raise ValueError("EMAIL_DOMAIN_MISMATCH")

        temp_password = secrets.token_urlsafe(12)
        oa_user_id = str(uuid.uuid4())

        await self._db.execute(
            """
            INSERT INTO oa_user
              (oa_user_id, tenant_id, email, role, temp_password_hash, force_reset, status, created_by)
            VALUES ($1,$2,$3,$4,$5,TRUE,'ACTIVE',$6)
            """,
            oa_user_id, tenant_id, email, role,
            hash_password(temp_password), created_by,
        )

        return {
            "oa_user_id": oa_user_id,
            "temp_password": temp_password,   # delivered via email, never stored again
        }

    async def deactivate(self, oa_user_id: str, tenant_id: str, actor_id: str) -> None:
        row = await self._db.fetchrow(
            "SELECT role FROM oa_user WHERE oa_user_id=$1 AND tenant_id=$2",
            oa_user_id, tenant_id,
        )
        if not row:
            raise ValueError("USER_NOT_FOUND")

        if row["role"] == "oa_admin":
            await self._check_min_admin(tenant_id, exclude_id=oa_user_id)

        await self._db.execute(
            "UPDATE oa_user SET status='DEACTIVATED' WHERE oa_user_id=$1", oa_user_id,
        )
        # Revoke all active sessions
        sessions = await self._db.fetch(
            "SELECT session_id FROM user_session WHERE user_type='oa_user' AND user_id=$1 AND revoked=FALSE",
            oa_user_id,
        )
        for s in sessions:
            await self._db.execute(
                "UPDATE user_session SET revoked=TRUE, revoked_reason='FORCE_LOGOUT' WHERE session_id=$1",
                s["session_id"],
            )

    async def change_role(self, oa_user_id: str, new_role: str, tenant_id: str, actor_id: str) -> None:
        row = await self._db.fetchrow(
            "SELECT role FROM oa_user WHERE oa_user_id=$1 AND tenant_id=$2",
            oa_user_id, tenant_id,
        )
        if not row:
            raise ValueError("USER_NOT_FOUND")

        # Demotion from oa_admin → check min-1-admin constraint
        if row["role"] == "oa_admin" and new_role != "oa_admin":
            await self._check_min_admin(tenant_id, exclude_id=oa_user_id)

        await self._db.execute(
            "UPDATE oa_user SET role=$2 WHERE oa_user_id=$1", oa_user_id, new_role,
        )

    async def unlock(self, oa_user_id: str, tenant_id: str, actor_id: str) -> None:
        await self._db.execute(
            "UPDATE oa_user SET status='ACTIVE', failed_totp_count=0 WHERE oa_user_id=$1 AND tenant_id=$2",
            oa_user_id, tenant_id,
        )
        await self._db.execute(
            """
            INSERT INTO account_status_event
              (user_type, user_id, tenant_id, event_type, from_status, to_status,
               reason_code, actor_type, actor_id, occurred_at)
            VALUES ('oa_user',$1,$2,'TOTP_LOCKOUT','LOCKED','ACTIVE','ADMIN_UNLOCK','oa_admin',$3,NOW())
            """,
            oa_user_id, tenant_id, actor_id,
        )

    async def list_for_tenant(self, tenant_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT oa_user_id, email, role, status, totp_configured_at,
                   last_login_at, force_reset, created_at
            FROM oa_user WHERE tenant_id=$1 ORDER BY role, email
            """,
            tenant_id,
        )
        return [
            {
                "oa_user_id": str(r["oa_user_id"]),
                "email": r["email"],
                "role": r["role"],
                "status": r["status"],
                "totp_configured_at": r["totp_configured_at"].isoformat() if r["totp_configured_at"] else None,
                "last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None,
                "force_reset": r["force_reset"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def _check_min_admin(self, tenant_id: str, exclude_id: str) -> None:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM oa_user
            WHERE tenant_id=$1 AND role='oa_admin' AND status='ACTIVE' AND oa_user_id != $2
            """,
            tenant_id, exclude_id,
        )
        if count < 1:
            raise ValueError("MIN_ADMIN_CONSTRAINT")
