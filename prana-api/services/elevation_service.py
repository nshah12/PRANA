"""
Elevation request lifecycle.
OA-Operator requests → OA-Admin approves → elevated session window opens.
All actions during window carry elevation_id in audit trail.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg


class ElevationService:

    def __init__(self, db: asyncpg.Connection):
        self._db = db

    async def request(
        self,
        requestor_id: str,
        tenant_id: str,
        reason: str,
        duration_hours: int,
    ) -> dict:
        if duration_hours not in (2, 4, 8):
            raise ValueError("INVALID_DURATION")

        # Only one pending request per operator at a time
        existing = await self._db.fetchrow(
            "SELECT elevation_id FROM elevation_request WHERE requestor_id=$1 AND status='PENDING'",
            requestor_id,
        )
        if existing:
            raise ValueError("PENDING_REQUEST_EXISTS")

        elevation_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO elevation_request
              (elevation_id, requestor_id, tenant_id, reason, duration_hours, status)
            VALUES ($1,$2,$3,$4,$5,'PENDING')
            """,
            elevation_id, requestor_id, tenant_id, reason, duration_hours,
        )
        return {"elevation_id": elevation_id, "status": "PENDING"}

    async def approve(self, elevation_id: str, approver_id: str, tenant_id: str) -> dict:
        row = await self._db.fetchrow(
            "SELECT requestor_id, duration_hours, status FROM elevation_request WHERE elevation_id=$1 AND tenant_id=$2",
            elevation_id, tenant_id,
        )
        if not row:
            raise ValueError("NOT_FOUND")
        if row["status"] != "PENDING":
            raise ValueError("NOT_PENDING")
        if str(row["requestor_id"]) == approver_id:
            raise ValueError("SELF_APPROVAL_NOT_ALLOWED")

        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=row["duration_hours"])
        await self._db.execute(
            """
            UPDATE elevation_request
            SET status='ACTIVE', approver_id=$2, approved_at=NOW(), expires_at=$3
            WHERE elevation_id=$1
            """,
            elevation_id, approver_id, expires_at,
        )
        return {"elevation_id": elevation_id, "status": "ACTIVE", "expires_at": expires_at.isoformat()}

    async def deny(self, elevation_id: str, approver_id: str, tenant_id: str) -> None:
        await self._db.execute(
            """
            UPDATE elevation_request
            SET status='DENIED', approver_id=$2, approved_at=NOW()
            WHERE elevation_id=$1 AND tenant_id=$3 AND status='PENDING'
            """,
            elevation_id, approver_id, tenant_id,
        )

    async def end_early(self, elevation_id: str, requestor_id: str, tenant_id: str) -> None:
        await self._db.execute(
            """
            UPDATE elevation_request SET status='ENDED_EARLY'
            WHERE elevation_id=$1 AND requestor_id=$2 AND tenant_id=$3 AND status='ACTIVE'
            """,
            elevation_id, requestor_id, tenant_id,
        )
        await self._db.execute(
            "INSERT INTO audit_event (event_type,actor_type,actor_id,tenant_id,event_metadata,occurred_at) "
            "VALUES ('ELEVATION_ENDED_EARLY','oa_user',$1,$2,$3,NOW())",
            requestor_id, tenant_id, {"elevation_id": elevation_id},
        )

    async def get_active(self, requestor_id: str) -> Optional[dict]:
        """Returns active elevation for a given OA-Operator, or None."""
        row = await self._db.fetchrow(
            """
            SELECT elevation_id, duration_hours, expires_at, approved_at
            FROM elevation_request
            WHERE requestor_id=$1 AND status='ACTIVE' AND expires_at > NOW()
            """,
            requestor_id,
        )
        return dict(row) if row else None

    async def list_pending(self, tenant_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT er.elevation_id, er.requestor_id, ou.email AS requestor_email,
                   er.reason, er.duration_hours, er.requested_at
            FROM elevation_request er
            JOIN oa_user ou ON ou.oa_user_id = er.requestor_id
            WHERE er.tenant_id=$1 AND er.status='PENDING'
            ORDER BY er.requested_at ASC
            """,
            tenant_id,
        )
        return [dict(r) for r in rows]
