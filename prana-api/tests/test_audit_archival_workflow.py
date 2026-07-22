"""Tests for workflows/compliance.py — AuditArchivalWorkflow schedule registration.

Regression: AuditArchivalWorkflow is documented (Pattern 3 — Temporal Schedule,
"Runs nightly") but had no ensure_*_schedule() function anywhere, and no
platform_config key for its own cadence (only audit_archival_cutoff_days /
audit_archival_batch_size, which control WHAT gets archived, not WHEN the
workflow itself runs). Never actually ran automatically.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_ensure_audit_archival_schedule_creates_real_schedule():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec
    from temporalio.service import RPCError, RPCStatusCode
    from workflows.compliance import AuditArchivalWorkflow, ensure_audit_archival_schedule

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_audit_archival_schedule(client, cron_expression="0 3 * * *")

    client.create_schedule.assert_awaited_once()
    schedule_id, schedule = client.create_schedule.await_args.args[:2]
    assert schedule_id == "audit-archival"
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "compliance-queue"
    assert schedule.spec.cron_expressions == ["0 3 * * *"]
    assert schedule.spec.time_zone_name == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_ensure_audit_archival_schedule_updates_existing_schedule_cron():
    from temporalio.client import (
        Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleUpdateInput, ScheduleUpdate,
    )
    from workflows.compliance import AuditArchivalWorkflow, ensure_audit_archival_schedule

    existing = Schedule(
        action=ScheduleActionStartWorkflow(AuditArchivalWorkflow.run, id="x", task_queue="compliance-queue"),
        spec=ScheduleSpec(cron_expressions=["0 0 * * *"]),
    )
    captured = {}

    async def fake_update(updater, **kw):
        desc = MagicMock()
        desc.schedule = existing
        captured["result"] = await updater(ScheduleUpdateInput(description=desc))

    handle = MagicMock()
    handle.describe = AsyncMock(return_value=None)
    handle.update = fake_update
    client = MagicMock()
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_audit_archival_schedule(client, cron_expression="0 3 * * *")

    client.create_schedule.assert_not_awaited()
    result = captured["result"]
    assert isinstance(result, ScheduleUpdate)
    assert result.schedule.spec.cron_expressions == ["0 3 * * *"]
