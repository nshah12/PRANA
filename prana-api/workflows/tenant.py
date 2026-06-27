"""
Tenant lifecycle workflows (admin-queue).

DomainVerificationWorkflow
  Triggered when PA creates a new tenant application.
  Polls DNS TXT record every `domain_verification_poll_minutes` (default 15).
  Times out after `domain_verification_max_hours` (default 48).
  On verified → signals TenantProvisioningWorkflow.
  On timeout  → marks tenant VERIFICATION_FAILED.

TenantProvisioningWorkflow
  Triggered by DomainVerificationWorkflow signal or directly by PA.
  Provisions: KMS KEK, first OA-Admin account (force_reset=TRUE), welcome email.
  Marks tenant ACTIVE on completion.

TenantOffboardingWorkflow
  Triggered when a tenant contract ends.
  Freezes all pushes, schedules vault handoff to employees, starts retention clock.

TenantMigrationWorkflow
  Moves all tenant data between regions (active → standby → active).
  Human-signal pattern: PA confirms before data cut-over.
"""
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "admin-queue"

_RETRY = RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=5))


@workflow.defn(name="DomainVerificationWorkflow")
class DomainVerificationWorkflow:
    def __init__(self) -> None:
        self._verified = False

    @workflow.signal
    async def domain_verified(self) -> None:
        self._verified = True

    @workflow.run
    async def run(self, params: dict) -> dict:
        tenant_id = params["tenant_id"]
        cfg = await workflow.execute_activity(
            "get_tenant_onboarding_config", {"tenant_id": tenant_id},
            start_to_close_timeout=timedelta(seconds=30), retry_policy=_RETRY,
        )
        verified = await self._poll_until_verified(
            tenant_id, params["domain"],
            poll_activity="check_dns_txt_record",
            poll_minutes=cfg["domain_verification_poll_minutes"],
            max_seconds=cfg["domain_verification_max_hours"] * 3600,
        )
        if not verified:
            await workflow.execute_activity(
                "mark_tenant_verification_failed", {"tenant_id": tenant_id},
                start_to_close_timeout=timedelta(seconds=30), retry_policy=_RETRY,
            )
            return {"tenant_id": tenant_id, "outcome": "VERIFICATION_FAILED"}
        await workflow.execute_activity(
            "provision_tenant", {"tenant_id": tenant_id},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        return {"tenant_id": tenant_id, "outcome": "PROVISIONED"}

    async def _poll_until_verified(self, tenant_id: str, domain: str,
                                   poll_activity: str, poll_minutes: int,
                                   max_seconds: int) -> bool:
        elapsed = 0
        while elapsed < max_seconds:
            result = await workflow.execute_activity(
                poll_activity, {"tenant_id": tenant_id, "domain": domain},
                start_to_close_timeout=timedelta(seconds=30), retry_policy=_RETRY,
            )
            if result["verified"] or self._verified:
                return True
            sleep_secs = poll_minutes * 60
            try:
                await asyncio.wait_for(
                    workflow.wait_condition(lambda: self._verified), timeout=sleep_secs,
                )
                return True
            except asyncio.TimeoutError:
                elapsed += sleep_secs
        return False


@workflow.defn(name="TenantProvisioningWorkflow")
class TenantProvisioningWorkflow:
    @workflow.run
    async def run(self, params: dict) -> dict:
        tenant_id = params["tenant_id"]

        await workflow.execute_activity(
            "provision_tenant",
            {"tenant_id": tenant_id},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return {"tenant_id": tenant_id, "outcome": "PROVISIONED"}


# ── TenantOffboardingWorkflow (Pattern 1 — Durable Timer) ────────────────────

@workflow.defn(name="TenantOffboardingWorkflow")
class TenantOffboardingWorkflow:
    """
    Triggered when a tenant contract terminates.
    1. Freeze all document pushes immediately
    2. Notify all employees: vault is now employee-owned permanently
    3. Start RetentionWorkflow for each employee's documents
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        await workflow.execute_activity(
            "freeze_tenant_pushes", params,
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            "notify_tenant_offboarding", params,
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            "start_employee_retention_for_tenant", params,
            start_to_close_timeout=timedelta(hours=1), retry_policy=_RETRY,
        )


# ── TenantMigrationWorkflow (Pattern 5 — Human Signal) ───────────────────────

@workflow.defn(name="TenantMigrationWorkflow")
class TenantMigrationWorkflow:
    """
    Moves all tenant data between YugabyteDB regions.
    Requires PA 'confirm_cutover' signal before final data cut-over.
    No confirmation within 72h → rollback.
    """

    def __init__(self):
        self._confirmed = False
        self._rolled_back = False

    @workflow.signal(name="confirm_cutover")
    def confirm_cutover(self, payload: dict) -> None:
        self._confirmed = True

    @workflow.signal(name="rollback_migration")
    def rollback_migration(self, payload: dict) -> None:
        self._rolled_back = True

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        await workflow.execute_activity(
            "prepare_migration", params,
            start_to_close_timeout=timedelta(hours=2), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            "notify_migration_ready", params,
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )
        confirmed = await workflow.wait_condition(
            lambda: self._confirmed or self._rolled_back,
            timeout=timedelta(hours=72),
        )
        if self._rolled_back or not confirmed:
            await workflow.execute_activity(
                "rollback_migration_prep", params,
                start_to_close_timeout=timedelta(hours=1), retry_policy=_RETRY,
            )
            return
        await workflow.execute_activity(
            "execute_migration_cutover", params,
            start_to_close_timeout=timedelta(hours=4),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
