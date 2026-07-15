"""
ErrorThresholdEvaluationWorkflow — Temporal Schedule (Pattern 3).

Periodically scans open error_event rows and promotes qualifying ones to
real incidents, per the rules in services/error_threshold_service.py and
prana-docs/ERROR_OBSERVABILITY_DESIGN.md §5.
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy


@activity.defn(name="evaluate_error_thresholds")
async def evaluate_error_thresholds() -> dict:
    import asyncpg

    from config import get_settings
    from services.error_threshold_service import ErrorThresholdService

    s = get_settings()
    conn = await asyncpg.connect(s.db_dsn)
    try:
        return await ErrorThresholdService(conn).evaluate_promotions()
    finally:
        await conn.close()


@workflow.defn(name="ErrorThresholdEvaluationWorkflow")
class ErrorThresholdEvaluationWorkflow:
    """
    Triggered by Temporal Schedule every `error_threshold_check_interval_minutes`
    (default: 15, from platform_config). Each run scans open error_event rows
    and promotes qualifying ones to incidents (see services/error_threshold_service.py).
    """

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            evaluate_error_thresholds,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


async def ensure_error_threshold_schedule(client, interval_minutes: int = 15) -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    from temporalio.client import ScheduleHandle
    from temporalio.service import RPCError
    from temporalio.common import (
        Schedule, ScheduleSpec, ScheduleIntervalSpec, ScheduleActionStartWorkflow,
    )

    schedule_id = "error-threshold-evaluation"
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        await handle.update(
            lambda s: s.with_spec(
                ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))])
            )
        )
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    ErrorThresholdEvaluationWorkflow.run,
                    task_queue="secops-queue",
                ),
                spec=ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))]
                ),
            ),
        )
