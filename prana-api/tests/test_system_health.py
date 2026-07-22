"""Tests for workflows/system_health.py — system health monitoring workflow."""
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock

from workflows.system_health import SystemHealthWorkflow, ensure_health_schedule


def test_system_health_workflow_is_thin_shell():
    src = inspect.getsource(SystemHealthWorkflow.run)
    assert "execute_activity" in src or "run_health_checks" in src, \
        "SystemHealthWorkflow must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"SystemHealthWorkflow.run has {len(non_comment)} lines — must be <20"


# ── Regression: ensure_health_schedule must actually call the real Temporal
# Schedule API — a prior version imported Schedule/ScheduleSpec/etc from
# temporalio.common (they live in temporalio.client), called a nonexistent
# Schedule.with_spec() method, and omitted ScheduleActionStartWorkflow's
# required id= — every one of those raises before ever reaching Temporal, but
# the only test in this file used inspect.getsource() string checks, which
# never actually calls the function and so never caught any of it. ─────────

@pytest.mark.asyncio
async def test_ensure_health_schedule_creates_real_schedule_on_first_run():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec
    from temporalio.service import RPCError, RPCStatusCode

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_health_schedule(client, interval_minutes=2)

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "system-health-check"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id, "ScheduleActionStartWorkflow requires a non-empty id"
    assert schedule.action.task_queue == "secops-queue"
    assert isinstance(schedule.spec, ScheduleSpec)
    assert schedule.spec.intervals == [ScheduleIntervalSpec(every=__import__("datetime").timedelta(minutes=2))]


@pytest.mark.asyncio
async def test_ensure_health_schedule_updates_existing_schedule_interval():
    import dataclasses
    from temporalio.client import (
        Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleUpdateInput, ScheduleUpdate,
    )
    from datetime import timedelta

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(return_value=None)
    existing = Schedule(
        action=ScheduleActionStartWorkflow(SystemHealthWorkflow.run, id="system-health-check-run", task_queue="secops-queue"),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=999))]),
    )
    captured = {}

    async def fake_update(updater, **kw):
        desc = MagicMock()
        desc.schedule = existing
        result = updater(ScheduleUpdateInput(description=desc))
        captured["result"] = await result if dataclasses.is_dataclass(result) is False and hasattr(result, "__await__") else result

    handle.update = fake_update
    client.get_schedule_handle = MagicMock(return_value=handle)

    await ensure_health_schedule(client, interval_minutes=5)

    result = captured["result"]
    assert isinstance(result, ScheduleUpdate)
    assert result.schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=5))]
