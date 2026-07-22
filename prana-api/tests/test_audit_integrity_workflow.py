"""Tests for workflows/audit_integrity.py — AuditIntegrityVerificationWorkflow."""
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock

from workflows.audit_integrity import AuditIntegrityVerificationWorkflow, ensure_audit_integrity_schedule


def test_audit_integrity_workflow_is_thin_shell():
    src = inspect.getsource(AuditIntegrityVerificationWorkflow.run)
    assert "execute_activity" in src or "verify_audit_integrity" in src, \
        "AuditIntegrityVerificationWorkflow must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"AuditIntegrityVerificationWorkflow.run has {len(non_comment)} lines — must be <20"


def test_ensure_schedule_is_idempotent_create_or_update():
    src = inspect.getsource(ensure_audit_integrity_schedule)
    assert "get_schedule_handle" in src
    assert "create_schedule" in src
    assert "task_queue=\"secops-queue\"" in src, \
        "AuditIntegrityVerificationWorkflow must run on secops-queue (see workflows/CLAUDE.md)"


# ── Regression: same class of bug as system_health.py's schedule registration
# (wrong import location, nonexistent with_spec() call, missing required id=)
# — none of it caught by the source-inspection test above since it never
# actually calls the function. ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_audit_integrity_schedule_creates_real_schedule_on_first_run():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec
    from temporalio.service import RPCError, RPCStatusCode
    from datetime import timedelta

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_audit_integrity_schedule(client, interval_minutes=60)

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "audit-integrity-verification"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id, "ScheduleActionStartWorkflow requires a non-empty id"
    assert schedule.action.task_queue == "secops-queue"
    assert schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=60))]


@pytest.mark.asyncio
async def test_ensure_audit_integrity_schedule_updates_existing_schedule_interval():
    from temporalio.client import (
        Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleUpdateInput, ScheduleUpdate,
    )
    from datetime import timedelta

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(return_value=None)
    existing = Schedule(
        action=ScheduleActionStartWorkflow(AuditIntegrityVerificationWorkflow.run, id="x", task_queue="secops-queue"),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=999))]),
    )
    captured = {}

    async def fake_update(updater, **kw):
        desc = MagicMock()
        desc.schedule = existing
        captured["result"] = await updater(ScheduleUpdateInput(description=desc))

    handle.update = fake_update
    client.get_schedule_handle = MagicMock(return_value=handle)

    await ensure_audit_integrity_schedule(client, interval_minutes=30)

    result = captured["result"]
    assert isinstance(result, ScheduleUpdate)
    assert result.schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=30))]
