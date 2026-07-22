"""
record_consumer_error — shared helper called from each Kafka consumer's outer
except block, alongside the existing log.exception() call (kept — the stderr
trace is still useful for live debugging).

Best-effort: never raises, never blocks the consumer's commit loop. Consumers
with no DB pool (Redis/Temporal-only, e.g. SSEFanoutConsumer, PlatformConsumer)
pass db_pool=None and this is a silent no-op for them — see
prana-docs/ERROR_OBSERVABILITY_DESIGN.md §4B.
"""
import logging

log = logging.getLogger(__name__)


async def record_consumer_error(
    db_pool,
    *,
    consumer_name: str,
    exc: Exception,
    event_type: str | None = None,
    event_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    if db_pool is None:
        return
    try:
        from services.error_observability_service import ErrorObservabilityService
        async with db_pool.acquire() as conn:
            await ErrorObservabilityService(conn).record(
                exc=exc,
                source="KAFKA_CONSUMER",
                source_detail=consumer_name,
                event_id=event_id,
                tenant_id=tenant_id,
            )
    except Exception:
        log.exception("record_consumer_error itself failed consumer=%s event_type=%s",
                       consumer_name, event_type)
