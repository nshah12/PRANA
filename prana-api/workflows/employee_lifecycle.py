"""
Employee lifecycle workflows — thin Temporal shells.
Business logic lives in services/employee_lifecycle_service.py (zero Temporal imports).

Task queues: admin-queue (exit, push-window, rejoin), vault-queue (activation, health, dormancy)

Workflows:
  EmployeeExitWorkflow      — triggered on exit: freeze vault, notify, start 7-yr retention
  PushWindowExpiryWorkflow  — close the push window after tenure
  VaultActivationWorkflow   — first-time vault setup for a new employee
  VaultHealthWorkflow       — recompute vault_completeness after every doc ROUTED event
  NomineeAccessWorkflow     — grant nominee time-limited access window
  RejoiningWorkflow         — employee re-joins same tenant: reconcile vault, re-link
  AccountDormancyWorkflow   — flag/freeze accounts with no login for X days
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Activities (stubs — implementations in services/employee_lifecycle_service.py) ──

@activity.defn(name="freeze_employee_vault")
async def freeze_employee_vault(params: dict) -> None: ...

@activity.defn(name="notify_exit_employee")
async def notify_exit_employee(params: dict) -> None: ...

@activity.defn(name="start_retention_workflow")
async def start_retention_workflow(params: dict) -> None: ...

@activity.defn(name="close_push_window")
async def close_push_window(params: dict) -> None: ...

@activity.defn(name="provision_vault")
async def provision_vault(params: dict) -> None: ...

@activity.defn(name="send_vault_welcome")
async def send_vault_welcome(params: dict) -> None: ...

@activity.defn(name="recompute_vault_completeness")
async def recompute_vault_completeness(params: dict) -> dict: ...

@activity.defn(name="grant_nominee_access")
async def grant_nominee_access(params: dict) -> None: ...

@activity.defn(name="revoke_nominee_access")
async def revoke_nominee_access(params: dict) -> None: ...

@activity.defn(name="reconcile_rejoining_employee")
async def reconcile_rejoining_employee(params: dict) -> None: ...

@activity.defn(name="flag_dormant_account")
async def flag_dormant_account(params: dict) -> None: ...

@activity.defn(name="get_lifecycle_config")
async def get_lifecycle_config(params: dict) -> str: ...


# ── EmployeeExitWorkflow (Pattern 1 — Durable Timer) ─────────────────────────

@workflow.defn(name="EmployeeExitWorkflow")
class EmployeeExitWorkflow:
    """
    Triggered when an employee's exit date is recorded.
    Freezes their vault (no new pushes), notifies them, and starts RetentionWorkflow
    for 7-year legal hold per DPDP + labour law requirements.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            freeze_employee_vault, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            notify_exit_employee, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            start_retention_workflow, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── PushWindowExpiryWorkflow (Pattern 1 — Durable Timer) ─────────────────────

@workflow.defn(name="PushWindowExpiryWorkflow")
class PushWindowExpiryWorkflow:
    """
    After the employer push window closes (typically 30 days post-exit),
    the vault is sealed: no further employer pushes accepted.
    Duration from config key 'push_window_days_after_exit'.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        days_str = await workflow.execute_activity(
            get_lifecycle_config,
            {"key": "push_window_days_after_exit", "tenant_id": params.get("tenant_id"), "default": "30"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.sleep(timedelta(days=int(days_str)))
        await workflow.execute_activity(
            close_push_window, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )


# ── VaultActivationWorkflow (Pattern 1 — fast, runs once) ────────────────────

@workflow.defn(name="VaultActivationWorkflow")
class VaultActivationWorkflow:
    """
    First-time vault setup for a newly resolved employee.
    Creates the vault record, provisions the DEK, sends welcome notification.
    Triggered by DocumentPipelineWorkflow stage 05 after identity resolution.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            provision_vault, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            send_vault_welcome, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── VaultHealthWorkflow (Pattern 1 — fast, runs on every ROUTED event) ───────

@workflow.defn(name="VaultHealthWorkflow")
class VaultHealthWorkflow:
    """
    Recomputes employee_master.vault_completeness after every document ROUTED.
    Lightweight: reads current document set, scores, writes score back to DB.
    Triggered by DocumentPipelineWorkflow stage 06.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            recompute_vault_completeness, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result


# ── NomineeAccessWorkflow (Pattern 1 — Durable Timer) ────────────────────────

@workflow.defn(name="NomineeAccessWorkflow")
class NomineeAccessWorkflow:
    """
    Grants a nominated contact (e.g. family member) time-limited read-only access
    to the employee's vault (e.g. after death/incapacitation).
    Window duration from config key 'nominee_access_window_days'.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        days_str = await workflow.execute_activity(
            get_lifecycle_config,
            {"key": "nominee_access_window_days", "tenant_id": params.get("tenant_id"), "default": "90"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.execute_activity(
            grant_nominee_access, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        await workflow.sleep(timedelta(days=int(days_str)))
        await workflow.execute_activity(
            revoke_nominee_access, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )


# ── RejoiningWorkflow (Pattern 1 — fast) ─────────────────────────────────────

@workflow.defn(name="RejoiningWorkflow")
class RejoiningWorkflow:
    """
    Employee re-joins the same tenant (re-hire).
    Reconciles the existing vault: un-freezes it, re-links to new employee_master
    row via pan_token dedup, sends re-hire welcome.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            reconcile_rejoining_employee, params,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            send_vault_welcome, {**params, "rejoin": True},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── AccountDormancyWorkflow (Pattern 1 — Durable Timer) ──────────────────────

@workflow.defn(name="AccountDormancyWorkflow")
class AccountDormancyWorkflow:
    """
    If an employee has not logged in for 'dormancy_threshold_days' (default: 365),
    flag the account as dormant and send a re-engagement notification.
    Runs once per employee; re-triggered on each login reset.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        days_str = await workflow.execute_activity(
            get_lifecycle_config,
            {"key": "dormancy_threshold_days", "tenant_id": params.get("tenant_id"), "default": "365"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.sleep(timedelta(days=int(days_str)))
        await workflow.execute_activity(
            flag_dormant_account, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
