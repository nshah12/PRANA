"""Tests for workflows/error_threshold.py — ErrorThresholdEvaluationWorkflow."""
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock

from workflows.error_threshold import ErrorThresholdEvaluationWorkflow, ensure_error_threshold_schedule


def test_error_threshold_workflow_is_thin_shell():
    src = inspect.getsource(ErrorThresholdEvaluationWorkflow.run)
    assert "execute_activity" in src or "evaluate_error_thresholds" in src
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper()
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"ErrorThresholdEvaluationWorkflow.run has {len(non_comment)} lines — must be <20"


def test_ensure_schedule_is_idempotent_create_or_update():
    src = inspect.getsource(ensure_error_threshold_schedule)
    assert "get_schedule_handle" in src
    assert "create_schedule" in src
    assert "task_queue=\"secops-queue\"" in src


# ── Regression: same class of bug as system_health.py / audit_integrity.py's
# schedule registration (wrong import location, nonexistent with_spec() call,
# missing required id=) — invisible to the source-inspection test above. ────

@pytest.mark.asyncio
async def test_ensure_error_threshold_schedule_creates_real_schedule_on_first_run():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec
    from temporalio.service import RPCError, RPCStatusCode
    from datetime import timedelta

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_error_threshold_schedule(client, interval_minutes=15)

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "error-threshold-evaluation"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id, "ScheduleActionStartWorkflow requires a non-empty id"
    assert schedule.action.task_queue == "secops-queue"
    assert schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=15))]


@pytest.mark.asyncio
async def test_ensure_error_threshold_schedule_updates_existing_schedule_interval():
    from temporalio.client import (
        Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleUpdateInput, ScheduleUpdate,
    )
    from datetime import timedelta

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(return_value=None)
    existing = Schedule(
        action=ScheduleActionStartWorkflow(ErrorThresholdEvaluationWorkflow.run, id="x", task_queue="secops-queue"),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=999))]),
    )
    captured = {}

    async def fake_update(updater, **kw):
        desc = MagicMock()
        desc.schedule = existing
        captured["result"] = await updater(ScheduleUpdateInput(description=desc))

    handle.update = fake_update
    client.get_schedule_handle = MagicMock(return_value=handle)

    await ensure_error_threshold_schedule(client, interval_minutes=20)

    result = captured["result"]
    assert isinstance(result, ScheduleUpdate)
    assert result.schedule.spec.intervals == [ScheduleIntervalSpec(every=timedelta(minutes=20))]
