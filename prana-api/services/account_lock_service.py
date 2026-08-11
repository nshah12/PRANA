"""
AccountLockService — business logic behind workflows/security.py's
apply_policy_lock / release_policy_lock activities (PolicyLockWorkflow, Pattern 2).

See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.3. Zero Temporal imports — same
shape as services/audit_integrity_service.py and services/anomaly_detection_service.py.
"""
import uuid
from typing import Optional


class AccountLockService:

    def __init__(self, db) -> None:
        self._db = db

    async def apply_policy_lock(
        self, *, user_type: str, user_id: str, tenant_id: Optional[str],
        reason_code: str, lock_hours: int,
    ) -> str:
        """Idempotent: an activity retry (Temporal at-least-once execution) after a
        successful-but-unacknowledged first attempt must not create a second lock
        row — return the existing OPEN one instead."""
        existing = await self._db.fetchval(
            "SELECT event_id FROM account_status_event "
            "WHERE user_type=$1 AND user_id=$2 AND event_type='POLICY_LOCK' "
            "AND reversed_by_event_id IS NULL",
            user_type, user_id,
        )
        if existing:
            return str(existing)

        event_id = uuid.uuid4()
        async with self._db.transaction():
            await self._db.execute(
                """
                INSERT INTO account_status_event
                  (event_id, event_type, user_type, user_id, tenant_id, from_status, to_status,
                   reason_code, actor_type, scheduled_unlock_at, occurred_at)
                VALUES ($1, 'POLICY_LOCK', $2, $3, $4, 'ACTIVE', 'LOCKED',
                        $5, 'SYSTEM', NOW() + ($6 || ' hours')::interval, NOW())
                """,
                event_id, user_type, user_id, tenant_id, reason_code, lock_hours,
            )
            await self._set_status(user_type, user_id, "LOCKED")
        return str(event_id)

    async def release_policy_lock(
        self, *, user_type: str, user_id: str, event_id: str,
        unlocked_by: str, early: bool,
    ) -> None:
        """Idempotent no-op if the lock was already reversed — the CISO manual-unlock
        endpoint (routers/ciso.py's manual_unlock) can beat this activity to the
        reversal when a CISO unlocks before the timer fires, since it writes
        reversed_by_event_id directly rather than signalling this workflow."""
        row = await self._db.fetchrow(
            "SELECT reversed_by_event_id FROM account_status_event WHERE event_id=$1",
            uuid.UUID(event_id),
        )
        if not row or row["reversed_by_event_id"]:
            return

        new_event_id = uuid.uuid4()
        async with self._db.transaction():
            await self._db.execute(
                """
                INSERT INTO account_status_event
                  (event_id, event_type, user_type, user_id, from_status, to_status,
                   reason_code, actor_type, actor_id, occurred_at)
                VALUES ($1, 'POLICY_LOCK_EXPIRED', $2, $3, 'LOCKED', 'ACTIVE',
                        'AUTO_UNLOCK', $4, $5, NOW())
                """,
                new_event_id, user_type, user_id,
                "CISO" if early else "SYSTEM",
                uuid.UUID(unlocked_by) if early and unlocked_by else None,
            )
            await self._db.execute(
                "UPDATE account_status_event SET reversed_by_event_id=$1 WHERE event_id=$2",
                new_event_id, uuid.UUID(event_id),
            )
            await self._set_status(user_type, user_id, "ACTIVE")
            # Without this, a user unlocked here whose very next TOTP attempt fails
            # immediately re-triggers the synchronous inline lock in
            # routers/auth_oa.py|auth_employee.py (stale failed_totp_count + 1 is
            # already >= threshold). Found 2026-08-10 while removing the redundant
            # TOTPLockoutWorkflow, whose release_totp_lockout used to do this reset
            # but was the only caller of it — this lock-release path (the one that's
            # actually live, via AuthConsumer) never did.
            await self._reset_failed_totp(user_type, user_id)

    # apply_totp_lockout / release_totp_lockout removed 2026-08-10 — backed
    # TOTPLockoutWorkflow (workflows/security.py), which was fully built but never
    # started by anything. The live TOTP-failure escalation path is
    # AuthConsumer._handle_totp_failure -> PolicyLockWorkflow -> apply_policy_lock/
    # release_policy_lock above.

    async def _set_status(self, user_type: str, user_id: str, status: str) -> None:
        if user_type == "employee":
            await self._db.execute(
                "UPDATE employee_user SET status=$1 WHERE employee_user_id=$2", status, user_id,
            )
        elif user_type == "oa_user":
            await self._db.execute(
                "UPDATE oa_user SET status=$1 WHERE oa_user_id=$2", status, user_id,
            )
        elif user_type == "portal_admin":
            await self._db.execute(
                "UPDATE portal_admin SET status=$1 WHERE pa_id=$2", status, user_id,
            )

    async def _reset_failed_totp(self, user_type: str, user_id: str) -> None:
        if user_type == "employee":
            await self._db.execute(
                "UPDATE employee_user SET failed_totp_count=0 WHERE employee_user_id=$1", user_id,
            )
        elif user_type == "oa_user":
            await self._db.execute(
                "UPDATE oa_user SET failed_totp_count=0 WHERE oa_user_id=$1", user_id,
            )
        elif user_type == "portal_admin":
            await self._db.execute(
                "UPDATE portal_admin SET failed_totp_count=0 WHERE pa_id=$1", user_id,
            )
