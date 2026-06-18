"""
ElevationWorkflow — durable timer for OA-Operator elevated sessions.

Lifecycle:
  1. OA-Operator requests elevation → INSERT elevation_request (PENDING)
  2. OA-Admin approves → signal 'admin_decision' → status=ACTIVE, expires_at set
  3. Workflow sleeps until expires_at (durable timer — survives worker restarts)
  4. On wake: marks EXPIRED, adds JWT to Redis revocation list
  5. OA-Operator may end early → signal 'end_early' → immediate expiry path

Signals:
  admin_decision(approved: bool, approver_id: str, duration_hours: int)
  end_early()

All durations come from the signal payload (set by AdminService from DB row).
No hardcoded durations here.
"""
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import logging

log = logging.getLogger(__name__)

TASK_QUEUE = "admin-queue"

_RETRY = RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=2))


@workflow.defn(name="ElevationWorkflow")
class ElevationWorkflow:
    def __init__(self) -> None:
        self._decision: dict | None = None
        self._end_early = False

    @workflow.signal
    async def admin_decision(self, payload: dict) -> None:
        self._decision = payload   # {"approved": bool, "approver_id": str, "duration_hours": int}

    @workflow.signal
    async def end_early(self) -> None:
        self._end_early = True

    @workflow.run
    async def run(self, params: dict) -> dict:
        elevation_id = params["elevation_id"]
        tenant_id    = params["tenant_id"]
        requestor_id = params["requestor_id"]

        # Wait up to 24h for admin decision
        await workflow.wait_condition(
            lambda: self._decision is not None,
            timeout=timedelta(hours=24),
        )

        if self._decision is None or not self._decision.get("approved"):
            # Timed out or denied — mark DENIED/EXPIRED and exit
            await workflow.execute_activity(
                "finalize_elevation",
                {
                    "elevation_id": elevation_id,
                    "status":       "DENIED" if (self._decision and not self._decision["approved"]) else "EXPIRED",
                    "approver_id":  (self._decision or {}).get("approver_id"),
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_RETRY,
            )
            return {"elevation_id": elevation_id, "outcome": "denied_or_timeout"}

        # Approved — activate in DB, get expires_at back
        duration_hours = self._decision["duration_hours"]
        approver_id    = self._decision["approver_id"]

        result = await workflow.execute_activity(
            "activate_elevation",
            {
                "elevation_id":  elevation_id,
                "approver_id":   approver_id,
                "duration_hours": duration_hours,
                "tenant_id":     tenant_id,
                "requestor_id":  requestor_id,
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )

        # Durable sleep until window expires (survives worker crash/restart)
        sleep_seconds = duration_hours * 3600
        try:
            await asyncio.wait_for(
                workflow.wait_condition(lambda: self._end_early),
                timeout=sleep_seconds,
            )
            ended_early = True
        except asyncio.TimeoutError:
            ended_early = False

        # Expire: mark DB + add JWT to Redis revocation list
        await workflow.execute_activity(
            "expire_elevation",
            {
                "elevation_id": elevation_id,
                "tenant_id":    tenant_id,
                "requestor_id": requestor_id,
                "ended_early":  ended_early,
                "jwt_jti":      params.get("jwt_jti"),   # passed at approve time
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )

        return {"elevation_id": elevation_id, "outcome": "ended_early" if ended_early else "expired"}
