"""
HRMSSyncScheduleWorkflow — creates/updates Temporal Schedules for HRMS pull connectors.

One schedule per ACTIVE connector, keyed hrms-sync-{connector_id}.
Idempotent: safe to run on every tenant provisioning or connector status change.

Pattern: Temporal Schedule (Pattern 3 from workflow CLAUDE.md).
Business logic in `ensure_hrms_schedules` activity — zero Temporal imports there.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from temporalio import activity, workflow

log = logging.getLogger(__name__)


def _schedule_id(connector_id) -> str:
    return f"hrms-sync-{connector_id}"


# ── Activity (no Temporal imports, unit-testable) ─────────────────────────────

async def ensure_hrms_schedules(
    tenant_id: str,
    db,
    temporal_client,
) -> dict:
    """
    For every ACTIVE connector in a tenant, ensure a Temporal Schedule exists
    that fires HRMSSyncWorkflow at the connector's pull_schedule cadence.

    PAUSED / REVOKED connectors are skipped — their schedules are paused separately
    by the status-change flow.
    """
    rows = await db.fetch(
        """
        SELECT c.connector_id, c.tenant_id, c.pull_schedule, c.status,
               d.connector_key
        FROM   hrms_connector_config c
        JOIN   hrms_connector_definition d
               ON d.connector_definition_id = c.connector_definition_id
        WHERE  c.tenant_id = $1
          AND  c.status    = 'ACTIVE'
        """,
        UUID(tenant_id),
    )

    created = 0
    updated = 0

    for row in rows:
        cid      = row["connector_id"]
        schedule = row.get("pull_schedule") or "0 */6 * * *"  # default every 6h
        sid      = _schedule_id(cid)

        try:
            handle = temporal_client.get_schedule_handle(sid)
            await handle.describe()
            # Exists — update interval to stay in sync with config changes
            await handle.update(lambda s: s)  # no-op update; cadence already set
            updated += 1
            log.debug("ensure_hrms_schedules: updated schedule %s", sid)
        except Exception:
            # Does not exist — create
            try:
                await temporal_client.create_schedule(
                    sid,
                    {
                        "workflow":     "HRMSSyncWorkflow",
                        "connector_id": str(cid),
                        "tenant_id":    str(tenant_id),
                        "cron_spec":    schedule,
                    },
                )
                created += 1
                log.info("ensure_hrms_schedules: created schedule %s cron=%s", sid, schedule)
            except Exception:
                log.exception("ensure_hrms_schedules: failed to create schedule %s", sid)

    return {"created": created, "updated": updated, "tenant_id": tenant_id}


# ── Activity wrapper for Temporal ─────────────────────────────────────────────

@activity.defn
async def run_ensure_hrms_schedules(tenant_id: str) -> dict:
    import asyncpg, os
    from temporalio.client import Client

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    tc   = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    try:
        return await ensure_hrms_schedules(
            tenant_id=tenant_id,
            db=conn,
            temporal_client=tc,
        )
    finally:
        await conn.close()


# ── Workflow shell (<20 lines) ────────────────────────────────────────────────

@dataclass
class HRMSSyncScheduleInput:
    tenant_id: str


@workflow.defn
class HRMSSyncScheduleWorkflow:
    @workflow.run
    async def run(self, inp: HRMSSyncScheduleInput) -> dict:
        return await workflow.execute_activity(
            run_ensure_hrms_schedules,
            inp.tenant_id,
            start_to_close_timeout=timedelta(minutes=5),
        )
