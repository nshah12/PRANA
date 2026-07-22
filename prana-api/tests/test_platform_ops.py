"""
Structural tests for workflows/platform_ops.py — Platform Operations workflows.

Covers:
  - PlatformSummaryWorkflow is a thin Temporal shell (Pattern 3 — Schedule)
    that reads interval from config, not hardcoded
  - ClamAVUpdateWorkflow uses Temporal schedule (Pattern 3) — no raw cron
"""
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock


def _get_source(cls_or_fn) -> str:
    return inspect.getsource(cls_or_fn)


# -- PlatformSummaryWorkflow -----------------------------------------------

def test_platform_summary_schedule_interval_from_config():
    """PlatformSummaryWorkflow must delegate to activities, not hardcode logic.
    The schedule interval is configured via 'platform_summary_interval_minutes' at
    schedule creation time (see workflows/CLAUDE.md Pattern 3) — never hardcoded.
    Verify the workflow class uses execute_activity and no raw sleep/polling.
    """
    from workflows.platform_ops import PlatformSummaryWorkflow

    source = _get_source(PlatformSummaryWorkflow.run)

    # Must use execute_activity — no business logic inline
    assert "execute_activity" in source, \
        "PlatformSummaryWorkflow must delegate to execute_activity"

    # Must call both metrics collection and write activities
    assert "collect_platform_metrics" in source, \
        "Must collect metrics via activity"
    assert "write_platform_summary" in source, \
        "Must write summary via activity"

    # Must not hardcode any duration
    assert "timedelta(days=" not in source, \
        "Duration must not be hardcoded in workflow shell"

    # No raw SQL
    assert "SELECT" not in source and "INSERT" not in source, \
        "No SQL in workflow shell"


def test_platform_summary_workflow_is_thin_shell():
    """PlatformSummaryWorkflow.run must be <20 lines (Temporal thin shell rule)."""
    from workflows.platform_ops import PlatformSummaryWorkflow

    lines = [
        l for l in _get_source(PlatformSummaryWorkflow.run).splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert len(lines) <= 20, \
        f"PlatformSummaryWorkflow.run has {len(lines)} lines — must be <20"


# ── Regression: PlatformSummaryWorkflow is documented (workflows/CLAUDE.md
# Pattern 3) as running on a Temporal Schedule, but no ensure_*_schedule()
# function existed anywhere for it — main.py's startup only ever registered
# schedules for SystemHealthWorkflow/AuditIntegrityVerificationWorkflow/
# ErrorThresholdEvaluationWorkflow. It has never actually run automatically. ─

@pytest.mark.asyncio
async def test_ensure_platform_summary_schedule_creates_real_schedule():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec
    from temporalio.service import RPCError, RPCStatusCode
    from datetime import timedelta
    from workflows.platform_ops import PlatformSummaryWorkflow, ensure_platform_summary_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_platform_summary_schedule(client, interval_minutes=5)

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "platform-summary"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "analytics-queue"
    assert schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=5))]


# -- KMSHealthCheckWorkflow -------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_kms_health_check_schedule_creates_real_schedule():
    """KMSHealthCheckWorkflow is documented (Pattern 3) but had no schedule
    registration anywhere — never actually ran."""
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec
    from temporalio.service import RPCError, RPCStatusCode
    from workflows.platform_ops import KMSHealthCheckWorkflow, ensure_kms_health_check_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_kms_health_check_schedule(client, cron_expression="0 2 * * *")

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "kms-health-check"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "secops-queue"
    assert schedule.spec.cron_expressions == ["0 2 * * *"]
    assert schedule.spec.time_zone_name == "Asia/Kolkata"


# -- StorageQuotaCheckWorkflow -----------------------------------------------

@pytest.mark.asyncio
async def test_ensure_storage_quota_check_schedule_creates_real_schedule():
    """StorageQuotaCheckWorkflow is documented (Pattern 3) but had no schedule
    registration anywhere — never actually ran."""
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec
    from temporalio.service import RPCError, RPCStatusCode
    from workflows.platform_ops import StorageQuotaCheckWorkflow, ensure_storage_quota_check_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_storage_quota_check_schedule(client, cron_expression="0 1 * * *")

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "storage-quota-check"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "analytics-queue"
    assert schedule.spec.cron_expressions == ["0 1 * * *"]
    assert schedule.spec.time_zone_name == "Asia/Kolkata"


# -- ClamAVUpdateWorkflow --------------------------------------------------

def test_clamav_update_workflow_uses_temporal_schedule():
    """ClamAVUpdateWorkflow must use execute_activity for signature pull.
    It runs on a Temporal Schedule (Pattern 3) — not a cron job or raw sleep loop.
    """
    from workflows.platform_ops import ClamAVUpdateWorkflow

    source = _get_source(ClamAVUpdateWorkflow.run)

    # Must delegate to an activity — no direct subprocess/shell calls
    assert "execute_activity" in source, \
        "ClamAVUpdateWorkflow must delegate to execute_activity"
    assert "pull_clamav_signatures" in source, \
        "Must call pull_clamav_signatures activity"

    # No raw OS calls or sleep
    assert "subprocess" not in source, "No subprocess in workflow shell"
    assert "asyncio.sleep" not in source, "Use workflow.sleep (durable), not asyncio.sleep"


def test_clamav_update_workflow_is_thin_shell():
    """ClamAVUpdateWorkflow.run must be <20 lines."""
    from workflows.platform_ops import ClamAVUpdateWorkflow

    lines = [
        l for l in _get_source(ClamAVUpdateWorkflow.run).splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert len(lines) <= 20, \
        f"ClamAVUpdateWorkflow.run has {len(lines)} lines — must be <20"


# ── Regression: ClamAVUpdateWorkflow was never registered on ANY worker task
# queue at all (not just missing a schedule) — even a manually-started
# workflow execution would sit forever with no worker to pick it up. Fixed
# alongside adding its schedule registration. ────────────────────────────────

def test_clamav_update_workflow_is_registered_on_a_worker_queue():
    from workflows.worker import WORKERS
    from workflows.platform_ops import ClamAVUpdateWorkflow, pull_clamav_signatures

    matches = [q for q, defn in WORKERS.items() if ClamAVUpdateWorkflow in defn["workflows"]]
    assert matches, "ClamAVUpdateWorkflow must be registered on at least one worker queue"
    assert pull_clamav_signatures in WORKERS[matches[0]]["activities"], \
        "pull_clamav_signatures activity must be registered on the same queue"


@pytest.mark.asyncio
async def test_ensure_clamav_update_schedule_creates_real_schedule():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleIntervalSpec
    from temporalio.service import RPCError, RPCStatusCode
    from datetime import timedelta
    from workflows.platform_ops import ClamAVUpdateWorkflow, ensure_clamav_update_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_clamav_update_schedule(client, interval_minutes=120)

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "clamav-update"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "ingestsvc-queue"
    assert schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=120))]


# ── Regression: same 0x-anywhere gap as ClamAVUpdateWorkflow. ────────────────

def test_staging_cleanup_workflow_is_registered_on_a_worker_queue():
    from workflows.worker import WORKERS
    from workflows.platform_ops import StagingCleanupWorkflow, purge_stale_staging_objects

    matches = [q for q, defn in WORKERS.items() if StagingCleanupWorkflow in defn["workflows"]]
    assert matches, "StagingCleanupWorkflow must be registered on at least one worker queue"
    assert purge_stale_staging_objects in WORKERS[matches[0]]["activities"], \
        "purge_stale_staging_objects activity must be registered on the same queue"


@pytest.mark.asyncio
async def test_ensure_staging_cleanup_schedule_creates_real_schedule():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow
    from temporalio.service import RPCError, RPCStatusCode
    from workflows.platform_ops import StagingCleanupWorkflow, ensure_staging_cleanup_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_staging_cleanup_schedule(client, cron_expression="0 4 * * *")

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "staging-cleanup"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "ingestsvc-queue"
    assert schedule.spec.cron_expressions == ["0 4 * * *"]
    assert schedule.spec.time_zone_name == "Asia/Kolkata"


# -- StorageExpansionWorkflow -----------------------------------------------

def test_storage_expansion_workflow_threads_request_id_and_decided_by():
    """Regression guard: _execute used to call notify_storage_expansion_request
    without capturing its return value, then pass the workflow's original params
    (with no request_id or decided_by) straight to apply/reject_storage_expansion —
    those activities have no way to know which storage_request row to update or
    who decided it without those fields."""
    from workflows.platform_ops import StorageExpansionWorkflow

    source = _get_source(StorageExpansionWorkflow._execute)
    assert "request_id = await workflow.execute_activity" in source, \
        "must capture notify_storage_expansion_request's return value"
    assert '"request_id": request_id' in source, \
        "request_id must be threaded into apply/reject_storage_expansion's params"
    assert '"decided_by": decided_by' in source, \
        "decided_by (the approving/rejecting actor) must be threaded through"
