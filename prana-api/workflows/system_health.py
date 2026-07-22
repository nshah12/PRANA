"""
SystemHealthWorkflow — Temporal Schedule (Pattern 3).

Polls all service /health endpoints every N minutes (from platform_config).
Creates service_incident rows on failure; auto-resolves on recovery.
Runs forever as a Temporal Schedule — no manual restart needed.
"""

from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy


@activity.defn(name="run_health_checks")
async def run_health_checks() -> list[dict]:
    import asyncpg
    from config import get_settings
    from services.health_service import HealthService

    s = get_settings()
    conn = await asyncpg.connect(s.db_dsn)
    try:
        svc = HealthService(conn)
        return await svc.run_checks()
    finally:
        await conn.close()


@workflow.defn(name="SystemHealthWorkflow")
class SystemHealthWorkflow:
    """
    Triggered by Temporal Schedule every `system_health_check_interval_minutes`
    (default: 2 min from platform_config). Each run pings all services and
    opens/resolves incidents.
    """

    @workflow.run
    async def run(self) -> list[dict]:
        return await workflow.execute_activity(
            run_health_checks,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=1),  # don't retry health checks
        )


async def ensure_health_schedule(client, interval_minutes: int = 2) -> None:
    """
    Called at prana-api startup to register the Temporal Schedule (idempotent).
    interval_minutes read from platform_config at startup.
    """
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "system-health-check"
    new_spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))])
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        # Already exists — update interval in case config changed
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    SystemHealthWorkflow.run,
                    id=f"{schedule_id}-run",
                    task_queue="secops-queue",
                ),
                spec=new_spec,
            ),
        )
