"""Tests for workflows/intelligence.py and AnomalyDetectionWorkflow."""
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock

from workflows.intelligence import CareerInsightWorkflow
from workflows.security import AnomalyDetectionWorkflow


def test_career_insight_workflow_is_thin_shell():
    src = inspect.getsource(CareerInsightWorkflow.run)
    assert "execute_activity" in src, \
        "CareerInsightWorkflow.run must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"


def test_anomaly_detection_uses_continue_as_new_before_history_limit():
    src = inspect.getsource(AnomalyDetectionWorkflow.run)
    assert "continue_as_new" in src, \
        "AnomalyDetectionWorkflow must use continue_as_new to keep history bounded"
    from workflows.security import RENEW_THRESHOLD
    assert RENEW_THRESHOLD > 0, "RENEW_THRESHOLD must be a positive integer"
    assert "RENEW_THRESHOLD" in src, \
        "AnomalyDetectionWorkflow must check RENEW_THRESHOLD before continuing as new"


# ── Regression: DigestWorkflow is documented (its own docstring + workflows/
# CLAUDE.md Pattern 3) as "Created once at startup as a Temporal Schedule",
# with weekly/monthly cadence from platform_config's digest_weekly_cron /
# digest_monthly_cron — but no ensure_*_schedule() function existed for it
# anywhere. Never actually ran automatically. ───────────────────────────────

@pytest.mark.asyncio
async def test_ensure_digest_schedules_creates_both_weekly_and_monthly():
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec
    from temporalio.service import RPCError, RPCStatusCode
    from workflows.intelligence import DigestWorkflow, ensure_digest_schedules

    client = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_digest_schedules(
        client, weekly_cron="0 6 * * MON", monthly_cron="0 6 1 * *",
    )

    assert client.create_schedule.await_count == 2
    calls = {call.args[0]: call.args[1] for call in client.create_schedule.await_args_list}

    assert "digest-weekly" in calls and "digest-monthly" in calls
    for sid, schedule in calls.items():
        assert isinstance(schedule, Schedule)
        assert isinstance(schedule.action, ScheduleActionStartWorkflow)
        assert schedule.action.id
        assert schedule.action.task_queue == "insight-queue"
        assert schedule.spec.time_zone_name == "Asia/Kolkata"

    assert calls["digest-weekly"].action.args[0]["digest_type"] == "weekly"
    assert calls["digest-weekly"].spec.cron_expressions == ["0 6 * * MON"]
    assert calls["digest-monthly"].action.args[0]["digest_type"] == "monthly"
    assert calls["digest-monthly"].spec.cron_expressions == ["0 6 1 * *"]
