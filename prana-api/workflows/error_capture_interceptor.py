"""
ErrorObservabilityInterceptor — records Temporal activity failures to
error_event, the 3rd capture layer of the 4th incident track (see
prana-docs/ERROR_OBSERVABILITY_DESIGN.md §4C).

Implementation note (deviation from the design doc's original wording):
the design doc said "record on final failure, not every transient retry."
In practice, Temporal gives an activity worker no way to know whether the
current attempt is the last one — RetryPolicy.maximum_attempts is set by
the calling workflow and is not exposed to ActivityInfo or
ExecuteActivityInput at execution time; only the Temporal server (which
decides whether to schedule another attempt) knows. So this interceptor
records every failed attempt instead. This is still not spam: recording
uses the SAME fingerprint-based dedup as the HTTP/Kafka layers
(ErrorObservabilityService.record()) — a Temporal activity that fails 3
times before eventually succeeding shows up as ONE error_event row with
occurrence_count=3, not three separate rows.

Re-raises unchanged in all cases — workflow retry/compensation/signal
behavior is completely unaffected by this interceptor.
"""
import logging
from typing import Any

from temporalio import activity
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
)

log = logging.getLogger(__name__)


async def _record(exc: Exception, activity_type: str) -> None:
    """Best-effort — opens its own short-lived DB connection since the
    Temporal worker process has no shared FastAPI-style db_pool. Never raises."""
    try:
        import asyncpg
        from config import get_settings
        from services.error_observability_service import ErrorObservabilityService

        s = get_settings()
        conn = await asyncpg.connect(s.db_dsn)
        try:
            await ErrorObservabilityService(conn).record(
                exc=exc,
                source="TEMPORAL_ACTIVITY",
                source_detail=activity_type,
            )
        finally:
            await conn.close()
    except Exception:
        log.exception("ErrorObservabilityInterceptor: failed to record activity_type=%s", activity_type)


class _RecordingActivityInboundInterceptor(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        try:
            return await self.next.execute_activity(input)
        except Exception as exc:
            activity_type = activity.info().activity_type
            await _record(exc, activity_type)
            raise


class ErrorObservabilityInterceptor(Interceptor):
    def intercept_activity(
        self, next: ActivityInboundInterceptor
    ) -> ActivityInboundInterceptor:
        return _RecordingActivityInboundInterceptor(next)
