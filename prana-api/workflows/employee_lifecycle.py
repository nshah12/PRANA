"""
Employee lifecycle workflows — thin Temporal shells.
Business logic lives in services/employee_lifecycle_service.py (zero Temporal imports).

Task queues (verified against worker.py's WORKERS map): admin-queue (exit,
push-window, activation, rejoin, dormancy), vault-queue (health, nominee access)

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


# ── Activities (implementations in services/employee_lifecycle_service.py) ──

@activity.defn(name="freeze_employee_vault")
async def freeze_employee_vault(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).freeze_employee_vault(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

async def _resolve_employee_user_id(params: dict) -> str | None:
    """EMPLOYEE_EXITED (routers/employees.py mark_alumni) only carries employee_uuid,
    not employee_user_id — notification activities that need a recipient_id resolve
    it here rather than requiring every caller to pre-thread it through."""
    if params.get("employee_user_id"):
        return params["employee_user_id"]
    if not params.get("employee_uuid"):
        return None
    import asyncpg

    from config import get_settings

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        row = await db.fetchrow(
            "SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1",
            params["employee_uuid"],
        )
        return str(row["employee_user_id"]) if row else None
    finally:
        await db.close()

@activity.defn(name="notify_exit_employee")
async def notify_exit_employee(params: dict) -> None:
    from kafka.producer import get_kafka_producer

    recipient_id = await _resolve_employee_user_id(params)
    kafka = await get_kafka_producer()
    await kafka.publish(
        "prana.notifications",
        {
            "event_type": "EMPLOYEE_EXITED",
            "recipient_id": recipient_id,
            "template_id": "EMPLOYEE_EXITED",
            "tenant_id": params.get("tenant_id"),
            "payload": {},
        },
        key=recipient_id,
    )

@activity.defn(name="start_retention_workflow")
async def start_retention_workflow(params: dict) -> None:
    """Starts the independent, long-running (7-year) RetentionWorkflow. Runs as a
    detached workflow, not a child workflow, since it must outlive EmployeeExitWorkflow
    — requires this activity to hold its own Temporal client, same as the pattern
    already used at startup in main.py."""
    from temporalio.client import Client as TemporalClient

    from config import get_settings

    settings = get_settings()
    client = await TemporalClient.connect(settings.temporal_host)
    employee_uuid = params["employee_uuid"]
    try:
        await client.start_workflow(
            "RetentionWorkflow",
            {"tenant_id": params.get("tenant_id"), "employee_uuid": employee_uuid,
             "scope": "EMPLOYEE_EXIT", "elapsed_years": 0},
            id=f"retention-employee-{employee_uuid}",
            task_queue="compliance-queue",
        )
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise

@activity.defn(name="start_push_window_expiry_workflow")
async def start_push_window_expiry_workflow(params: dict) -> None:
    """Starts the independent PushWindowExpiryWorkflow (30-day employer push
    grace period, then close_push_window). Detached, same shape as
    start_retention_workflow right above — must outlive EmployeeExitWorkflow."""
    from temporalio.client import Client as TemporalClient

    from config import get_settings

    settings = get_settings()
    client = await TemporalClient.connect(settings.temporal_host)
    employee_uuid = params["employee_uuid"]
    try:
        await client.start_workflow(
            "PushWindowExpiryWorkflow",
            {"tenant_id": params.get("tenant_id"), "employee_uuid": employee_uuid},
            id=f"push-window-expiry-{employee_uuid}",
            task_queue="admin-queue",
        )
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise

@activity.defn(name="close_push_window")
async def close_push_window(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).close_push_window(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="provision_vault")
async def provision_vault(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).provision_vault(
            employee_user_id=params["employee_user_id"],
        )
    finally:
        await db.close()

@activity.defn(name="send_vault_welcome")
async def send_vault_welcome(params: dict) -> None:
    from kafka.producer import get_kafka_producer

    kafka = await get_kafka_producer()
    template = "VAULT_WELCOME_REJOIN" if params.get("rejoin") else "VAULT_WELCOME"
    await kafka.publish(
        "prana.notifications",
        {
            "event_type": template,
            "recipient_id": params.get("employee_user_id"),
            "template_id": template,
            "tenant_id": params.get("tenant_id"),
            "payload": {},
        },
        key=params.get("employee_user_id"),
    )

@activity.defn(name="recompute_vault_completeness")
async def recompute_vault_completeness(params: dict) -> dict:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        return await EmployeeLifecycleService(db).recompute_vault_completeness(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="grant_nominee_access")
async def grant_nominee_access(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).grant_nominee_access(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
            window_days=int(params["window_days"]),
        )
    finally:
        await db.close()

@activity.defn(name="revoke_nominee_access")
async def revoke_nominee_access(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).revoke_nominee_access(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="reconcile_rejoining_employee")
async def reconcile_rejoining_employee(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).reconcile_rejoining_employee(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="flag_dormant_account")
async def flag_dormant_account(params: dict) -> None:
    import asyncpg

    from config import get_settings
    from services.employee_lifecycle_service import EmployeeLifecycleService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await EmployeeLifecycleService(db).flag_dormant_account(
            employee_user_id=params["employee_user_id"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="get_lifecycle_config")
async def get_lifecycle_config(params: dict) -> str:
    """Shared config-read activity for every workflow in this file — resolves
    tenant_config-overrides-platform_config via ConfigService, falling back to
    params["default"] only if the key is unset in the DB entirely."""
    import asyncpg
    import redis.asyncio as redis_async

    from config import get_settings
    from services.config_service import ConfigService

    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    rdb = redis_async.from_url(settings.redis_url)
    try:
        value = await ConfigService(db, rdb).get(params["key"], params.get("tenant_id"))
        return value if value is not None else params.get("default", "")
    finally:
        await db.close()
        await rdb.aclose()

@activity.defn(name="send_alumni_consent_prompt")
async def send_alumni_consent_prompt(params: dict) -> None:
    """Notify ex-employee via push + email: stay connected with your former employer?"""
    from kafka.producer import get_kafka_producer

    recipient_id = await _resolve_employee_user_id(params)
    kafka = await get_kafka_producer()
    await kafka.publish(
        "prana.notifications",
        {
            "event_type": "ALUMNI_CONSENT_PROMPT",
            "recipient_id": recipient_id,
            "template_id": "ALUMNI_CONSENT_PROMPT",
            "tenant_id": params.get("tenant_id"),
            "payload": {},
        },
        key=recipient_id,
    )


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
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            notify_exit_employee, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        await self._start_detached_followups(params)
        await workflow.execute_activity(
            send_alumni_consent_prompt, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )

    async def _start_detached_followups(self, params: dict) -> None:
        """Independent, longer-lived workflows that must outlive this one."""
        await workflow.execute_activity(
            start_retention_workflow, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            start_push_window_expiry_workflow, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
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
            grant_nominee_access, {**params, "window_days": days_str},
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
