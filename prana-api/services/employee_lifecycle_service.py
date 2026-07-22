"""
EmployeeLifecycleService — business logic behind workflows/employee_lifecycle.py's
activities (EmployeeExitWorkflow, VaultActivationWorkflow, VaultHealthWorkflow,
NomineeAccessWorkflow, RejoiningWorkflow, AccountDormancyWorkflow, PushWindowExpiryWorkflow).

Zero Temporal imports — same shape as services/account_lock_service.py.
"""
import uuid
from datetime import date, timedelta
from typing import Optional

# Core document types used as the vault-completeness baseline — a defensible v1
# metric covering the joining/pay/tax/exit lifecycle stages. Not a substitute for
# the richer per-role scoring VaultCompletenessWorkflow (workflows/intelligence.py)
# is meant to own once that file's stubs are implemented.
_CORE_DOC_TYPES = ("OFFER_LETTER", "SALARY_SLIP", "FORM_16", "RELIEVING_LETTER")


class EmployeeLifecycleService:

    def __init__(self, db) -> None:
        self._db = db

    async def freeze_employee_vault(self, *, employee_uuid: str, tenant_id: Optional[str]) -> None:
        """Immediate freeze at exit: blocks further employer pushes and force-logs-out
        any active session. Idempotent — re-running on an already-frozen row is a no-op."""
        await self._db.execute(
            "UPDATE employee_master SET can_push=FALSE, updated_at=NOW() "
            "WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )
        row = await self._db.fetchrow(
            "SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )
        if not row:
            return
        employee_user_id = str(row["employee_user_id"])
        await self._db.execute(
            "UPDATE user_session SET revoked=TRUE, revoked_reason='EMPLOYEE_EXIT' "
            "WHERE user_type='employee' AND user_id=$1 AND revoked=FALSE",
            employee_user_id,
        )

    async def close_push_window(self, *, employee_uuid: str, tenant_id: Optional[str]) -> None:
        """Later, config-driven closure (PushWindowExpiryWorkflow) — same end state as
        freeze_employee_vault's immediate can_push=FALSE, re-affirmed here in case this
        path fires independently of an exit (e.g. push window closed without a formal
        exit event)."""
        await self._db.execute(
            "UPDATE employee_master SET can_push=FALSE, updated_at=NOW() "
            "WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )

    async def provision_vault(self, *, employee_user_id: str) -> None:
        """First-time activation: PENDING_ACTIVATION -> ACTIVE. Idempotent via the
        WHERE clause — replays of this activity after a successful-but-unacknowledged
        attempt are a no-op.

        Guarded on having a login handle: chk_eu_login_handle (schema.sql) requires
        mobile OR email once status leaves PENDING_ACTIVATION. An employee created
        without either (employer supplied no contact info at push time) stays
        PENDING_ACTIVATION here rather than the UPDATE failing the CHECK constraint —
        activation for that row waits until an OA-Admin backfills a contact handle."""
        await self._db.execute(
            "UPDATE employee_user SET status='ACTIVE', activated_at=NOW() "
            "WHERE employee_user_id=$1 AND status='PENDING_ACTIVATION' "
            "AND (mobile IS NOT NULL OR email IS NOT NULL)",
            employee_user_id,
        )

    async def reconcile_rejoining_employee(self, *, employee_uuid: str, tenant_id: Optional[str]) -> None:
        """Un-freezes the vault after a re-hire. The ACTIVE/dol/push_window_expires
        transition itself already happened synchronously in EmployeeService.reactivate
        (routers/employees.py) before EMPLOYEE_REJOINED was published — this only
        reverses the can_push=FALSE that freeze_employee_vault set at the prior exit."""
        await self._db.execute(
            "UPDATE employee_master SET can_push=TRUE, updated_at=NOW() "
            "WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )

    async def recompute_vault_completeness(self, *, employee_uuid: str, tenant_id: Optional[str]) -> dict:
        rows = await self._db.fetch(
            "SELECT DISTINCT doc_type FROM document "
            "WHERE employee_uuid=$1 AND tenant_id=$2 AND pipeline_status='ROUTED' AND is_deleted=FALSE",
            employee_uuid, tenant_id,
        )
        present = {r["doc_type"] for r in rows}
        covered = sum(1 for t in _CORE_DOC_TYPES if t in present)
        score = round(covered / len(_CORE_DOC_TYPES) * 100, 2)
        await self._db.execute(
            "UPDATE employee_master SET vault_completeness=$2, updated_at=NOW() WHERE employee_uuid=$1",
            employee_uuid, score,
        )
        return {"vault_completeness": score}

    async def grant_nominee_access(self, *, employee_uuid: str, tenant_id: Optional[str], window_days: int) -> None:
        row = await self._db.fetchrow(
            "SELECT pan_token FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )
        if not row:
            return
        await self._db.execute(
            "UPDATE nominee SET activated_at=NOW(), access_expires_at=NOW() + ($2 || ' days')::interval "
            "WHERE pan_token=$1 AND id_verified=TRUE",
            row["pan_token"], window_days,
        )

    async def revoke_nominee_access(self, *, employee_uuid: str, tenant_id: Optional[str]) -> None:
        row = await self._db.fetchrow(
            "SELECT pan_token FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )
        if not row:
            return
        await self._db.execute(
            "UPDATE nominee SET access_expires_at=NOW() WHERE pan_token=$1",
            row["pan_token"],
        )

    async def flag_dormant_account(self, *, employee_user_id: str, tenant_id: Optional[str]) -> None:
        """Soft flag, not a lock — from_status==to_status='ACTIVE' distinguishes this
        from a real POLICY_LOCK/TOTP_LOCKOUT row in account_status_event. Idempotent:
        skip if a still-open dormancy flag already exists for this user."""
        existing = await self._db.fetchval(
            "SELECT event_id FROM account_status_event "
            "WHERE user_type='employee' AND user_id=$1 AND event_type='ACCOUNT_DORMANT' "
            "AND reversed_by_event_id IS NULL",
            employee_user_id,
        )
        if existing:
            return
        await self._db.execute(
            """
            INSERT INTO account_status_event
              (event_id, event_type, user_type, user_id, tenant_id, from_status, to_status,
               reason_code, actor_type, occurred_at)
            VALUES ($1, 'ACCOUNT_DORMANT', 'employee', $2, $3, 'ACTIVE', 'ACTIVE',
                    'DORMANCY_THRESHOLD_EXCEEDED', 'SYSTEM', NOW())
            """,
            uuid.uuid4(), employee_user_id, tenant_id,
        )
