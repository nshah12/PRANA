"""
AuditIntegrityVerificationWorkflow — Temporal Schedule (Pattern 3).

Periodically re-verifies recent audit_event rows against their Immudb
dual-write to catch tampering applied directly against YugabyteDB. Immudb's
verified_get() can PROVE a row was altered after the fact, but only if
something actually calls it on a schedule — that's what makes tampering
actually get noticed rather than just theoretically detectable. See
KAFKA_REDIS_ARCHITECTURE.md §8 and prana-db/migrations/039_audit_role_revoke.sql.
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy


@activity.defn(name="verify_audit_integrity")
async def verify_audit_integrity() -> dict:
    import asyncpg

    from config import get_settings
    from kafka.producer import get_kafka_producer
    from services.audit_integrity_service import AuditIntegrityService
    from services.immudb_service import ImmudbService

    s = get_settings()
    conn = await asyncpg.connect(s.db_dsn)
    immudb = ImmudbService(
        host=s.immudb_host, port=s.immudb_port,
        user=s.immudb_user, password=s.immudb_password, database=s.immudb_database,
    )
    try:
        try:
            kafka = await get_kafka_producer()
        except Exception:
            kafka = None
        svc = AuditIntegrityService(conn, immudb, kafka)
        return await svc.verify_recent()
    finally:
        immudb.close()
        await conn.close()


@workflow.defn(name="AuditIntegrityVerificationWorkflow")
class AuditIntegrityVerificationWorkflow:
    """
    Triggered by Temporal Schedule every `audit_integrity_check_interval_minutes`
    (default: 60, from platform_config). Each run re-verifies the most recent
    500 audit_event rows against Immudb and publishes an AUDIT_INTEGRITY_MISMATCH
    security_event (notifying all active PA Admins) on any mismatch.
    """

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            verify_audit_integrity,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


async def ensure_audit_integrity_schedule(client, interval_minutes: int = 60) -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "audit-integrity-verification"
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
                    AuditIntegrityVerificationWorkflow.run,
                    id=f"{schedule_id}-run",
                    task_queue="secops-queue",
                ),
                spec=new_spec,
            ),
        )
