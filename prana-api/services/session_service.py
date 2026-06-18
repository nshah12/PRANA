import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg

from services.jwt_service import JWTService


class SessionService:
    """
    Creates, enforces limits on, and revokes user sessions.
    Max 5 concurrent sessions per user — 6th login revokes the oldest.
    session_id = JWT JTI claim = user_session.session_id (primary key).
    """

    def __init__(self, db: asyncpg.Connection, jwt_service: JWTService):
        self._db = db
        self._jwt = jwt_service

    async def create(
        self,
        *,
        user_type: str,
        user_id: str,
        tenant_id: Optional[str],
        role: Optional[str],
        ip_address: str,
        user_agent: str,
        jwt_ttl_minutes: int = 60,
        refresh_ttl_days: int = 7,
        max_concurrent: int = 5,
    ) -> dict:
        """
        Creates a session row, enforces concurrent session limit, issues JWT.
        Returns {access_token, refresh_token, session_id, expires_at}.
        refresh_token is plaintext (shown once) — SHA-256 hash stored in DB.
        """
        # Enforce concurrent session limit: revoke oldest if at max
        await self._enforce_limit(user_type, user_id, max_concurrent)

        session_id = str(secrets.token_hex(16))   # 128-bit random session ID = JWT JTI
        refresh_token = secrets.token_urlsafe(48)
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        now = datetime.now(tz=timezone.utc)
        jwt_expires = now + timedelta(minutes=jwt_ttl_minutes)
        refresh_expires = now + timedelta(days=refresh_ttl_days)

        await self._db.execute(
            """
            INSERT INTO user_session
              (session_id, user_type, user_id, refresh_token_hash,
               ip_address, user_agent, jwt_expires_at, refresh_expires_at)
            VALUES ($1,$2,$3,$4,$5::inet,$6,$7,$8)
            """,
            session_id, user_type, user_id, refresh_hash,
            ip_address, user_agent, jwt_expires, refresh_expires,
        )

        access_token = self._jwt.issue(
            user_type=user_type,
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            session_id=session_id,
            ttl_minutes=jwt_ttl_minutes,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,   # caller sets this as httpOnly cookie
            "session_id": session_id,
            "expires_at": jwt_expires.isoformat(),
        }

    async def revoke(self, session_id: str, reason: str = "LOGOUT") -> None:
        await self._db.execute(
            "UPDATE user_session SET revoked=TRUE, revoked_reason=$2 WHERE session_id=$1",
            session_id, reason,
        )
        await self._jwt.revoke(session_id)

    async def rotate_refresh(
        self,
        refresh_token: str,
        ip_address: str,
        jwt_ttl_minutes: int = 60,
        refresh_ttl_days: int = 7,
    ) -> Optional[dict]:
        """
        Validates refresh token, revokes old session, issues new session.
        Returns None if token not found or already revoked.
        """
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        row = await self._db.fetchrow(
            """
            SELECT session_id, user_type, user_id, refresh_expires_at, revoked
            FROM user_session
            WHERE refresh_token_hash = $1
            """,
            refresh_hash,
        )
        if not row or row["revoked"]:
            return None
        if row["refresh_expires_at"] < datetime.now(tz=timezone.utc):
            return None

        # Need user details for new JWT — fetch from appropriate table
        user_row = await self._fetch_user(row["user_type"], row["user_id"])
        if not user_row:
            return None

        await self.revoke(row["session_id"], reason="REFRESHED")

        return await self.create(
            user_type=row["user_type"],
            user_id=str(row["user_id"]),
            tenant_id=user_row.get("tenant_id"),
            role=user_row.get("role"),
            ip_address=ip_address,
            user_agent="",
            jwt_ttl_minutes=jwt_ttl_minutes,
            refresh_ttl_days=refresh_ttl_days,
        )

    async def _enforce_limit(self, user_type: str, user_id: str, max_concurrent: int) -> None:
        rows = await self._db.fetch(
            """
            SELECT session_id FROM user_session
            WHERE user_type=$1 AND user_id=$2 AND revoked=FALSE
              AND refresh_expires_at > NOW()
            ORDER BY created_at ASC
            """,
            user_type, user_id,
        )
        if len(rows) >= max_concurrent:
            oldest = rows[0]["session_id"]
            await self.revoke(oldest, reason="SESSION_LIMIT")

    async def _fetch_user(self, user_type: str, user_id: str) -> Optional[dict]:
        if user_type == "employee":
            row = await self._db.fetchrow(
                "SELECT NULL::uuid AS tenant_id, NULL AS role FROM employee_user WHERE employee_user_id=$1",
                user_id,
            )
        elif user_type == "oa_user":
            row = await self._db.fetchrow(
                "SELECT tenant_id, role FROM oa_user WHERE oa_user_id=$1",
                user_id,
            )
        elif user_type == "portal_admin":
            row = await self._db.fetchrow(
                "SELECT NULL::uuid AS tenant_id, 'portal_admin' AS role FROM portal_admin WHERE pa_id=$1",
                user_id,
            )
        else:
            return None
        return dict(row) if row else None
