"""
Tests for kafka/consumers/audit_consumer.py — Wave 8: Kafka audit consumer batch commit.

Per-message commit means one Kafka round-trip per audit event. Under high ingest
(20K docs/batch) this creates a serialised commit bottleneck that limits audit
throughput to Kafka round-trip latency × message count.

Micro-batch fix: commit every BATCH_SIZE messages (default 500) or FLUSH_SECS
seconds (default 5), whichever comes first. Under failure, flush pending offsets
then skip the failed message so the consumer doesn't stall.

Also covers _parse_occurred_at(): every kafka.publish() call in this codebase
sends occurred_at as an ISO string, but asyncpg's binary protocol encodes bound
parameters per the prepared statement's inferred type — a ::timestamptz
parameter rejects a plain str regardless of the SQL-side cast. This was
actively crashing in production logs until fixed.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch, PropertyMock
import pytest


def _make_msg(offset: int, event_type: str = "DOC_INGESTED") -> MagicMock:
    msg = MagicMock()
    msg.topic = "prana.audit.events"
    msg.partition = 0
    msg.offset = offset
    msg.value = {"event_type": event_type, "tenant_id": "t-1", "document_id": f"doc-{offset}"}
    return msg


def _make_consumer():
    from kafka.consumers.audit_consumer import AuditConsumer

    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"

    db_pool = MagicMock()
    conn_ctx = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    db_pool.acquire = MagicMock(return_value=conn_ctx)

    with patch("kafka.consumers.audit_consumer.AIOKafkaConsumer"):
        consumer = AuditConsumer(settings, db_pool)

    kafka_mock = AsyncMock()
    kafka_mock.commit = AsyncMock()
    kafka_mock.stop = AsyncMock()
    consumer._consumer = kafka_mock

    return consumer, kafka_mock


@pytest.mark.asyncio
async def test_audit_consumer_commit_batched_not_per_message():
    """
    500 messages should produce far fewer than 500 commit() calls.
    Optimal: 1 commit for 500 messages. Acceptable: ≤ ceil(500/BATCH_SIZE) commits.
    RED: fails as long as per-message commit() is in place.
    """
    consumer, kafka_mock = _make_consumer()

    N = 500
    messages = [_make_msg(i) for i in range(N)]
    consumer._write_audit = AsyncMock()
    consumer._write_access_log = AsyncMock()

    async def fake_iter():
        for msg in messages:
            yield msg

    kafka_mock.__aiter__ = lambda self: fake_iter()
    kafka_mock.start = AsyncMock()

    # Run just the batch-loop logic — bypass start/stop so we can inspect commit count
    await consumer._run_loop(messages)

    commit_count = kafka_mock.commit.call_count
    assert commit_count < N, (
        f"commit() was called {commit_count} times for {N} messages. "
        "Must batch commits — not one per message."
    )
    # Generous upper bound: at most N/100 commits (allows various batch sizes ≥ 100)
    assert commit_count <= N // 100 + 1, (
        f"Too many commits ({commit_count}) for {N} messages. "
        "Batch size must be ≥ 100 messages."
    )


@pytest.mark.asyncio
async def test_audit_consumer_commits_all_pending_on_db_failure():
    """
    If a DB write fails, all pending-but-unwritten offsets must be committed
    before skipping the failed message — otherwise the consumer re-processes
    already-written messages on restart.
    RED: fails until error-path flushes pending offsets.
    """
    consumer, kafka_mock = _make_consumer()

    good_msg = _make_msg(0)
    bad_msg = _make_msg(1)

    write_calls = 0

    async def sometimes_fail(event):
        nonlocal write_calls
        write_calls += 1
        if event.get("document_id") == "doc-1":
            raise Exception("simulated DB write failure")

    consumer._write_audit = sometimes_fail
    consumer._write_access_log = AsyncMock()

    # Simulate 2 messages — first succeeds, second fails
    await consumer._run_loop([good_msg, bad_msg])

    # Commit must have been called at some point (to flush the good message)
    assert kafka_mock.commit.called, (
        "AuditConsumer must call commit() to flush pending good messages "
        "before skipping a failed one."
    )


@pytest.mark.asyncio
async def test_audit_consumer_exposes_run_loop_method():
    """
    _run_loop(messages) must be a testable method separate from the full run() lifecycle.
    This is the standard pattern for consumer unit testing without actual Kafka connections.
    RED: fails until _run_loop is extracted from run().
    """
    from kafka.consumers.audit_consumer import AuditConsumer
    assert hasattr(AuditConsumer, "_run_loop"), (
        "AuditConsumer must expose _run_loop(messages) for unit testing. "
        "This separates the batch-commit logic from Kafka connection management."
    )


# ── Immudb dual-write ─────────────────────────────────────────────────────────
# All audit events platform-wide must also land in the tamper-evident Immudb
# ledger, not just YugabyteDB's (ordinarily mutable) audit_event table.

def _make_consumer_with_fetchrow(fetchrow_return, immudb_service=None):
    from kafka.consumers.audit_consumer import AuditConsumer

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("kafka.consumers.audit_consumer.AIOKafkaConsumer"):
        settings = MagicMock()
        settings.kafka_bootstrap_servers = "localhost:9092"
        consumer = AuditConsumer(settings, mock_pool, immudb_service=immudb_service)

    return consumer, mock_conn


@pytest.mark.asyncio
async def test_write_audit_dual_writes_to_immudb_when_configured():
    """Every audit_event write must also land in Immudb under a deterministic key."""
    mock_immudb = MagicMock()
    mock_immudb.verified_set = MagicMock(return_value={"id": 1, "verified": True})
    consumer, mock_conn = _make_consumer_with_fetchrow(
        {"event_id": "evt-123"}, immudb_service=mock_immudb,
    )

    event = {
        "event_type": "ELEVATION_APPROVED",
        "tenant_id": "t-1",
        "actor_id": "oa-1",
        "actor_type": "OA_ADMIN",
    }
    await consumer._write_audit(event)

    mock_immudb.verified_set.assert_called_once()
    key, value = mock_immudb.verified_set.call_args[0]
    assert key == "audit:evt-123"
    assert value["event_id"] == "evt-123"
    assert value["event_type"] == "ELEVATION_APPROVED"


@pytest.mark.asyncio
async def test_write_audit_immudb_failure_does_not_raise_or_block_yugabyte_write():
    """Immudb is a secondary tamper-evident ledger — its failure must never break
    the primary audit_event write path."""
    mock_immudb = MagicMock()
    mock_immudb.verified_set = MagicMock(side_effect=RuntimeError("immudb unreachable"))
    consumer, mock_conn = _make_consumer_with_fetchrow(
        {"event_id": "evt-999"}, immudb_service=mock_immudb,
    )

    await consumer._write_audit({"event_type": "DOC_ROUTED", "tenant_id": "t-1"})  # must not raise

    mock_conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_write_audit_skips_immudb_when_not_configured():
    """Backward compatible: no immudb_service passed → no dual-write attempted."""
    consumer, mock_conn = _make_consumer_with_fetchrow({"event_id": "evt-1"})

    await consumer._write_audit({"event_type": "DOC_INGESTED", "tenant_id": "t-1"})

    assert consumer._immudb is None


@pytest.mark.asyncio
async def test_write_audit_skips_immudb_when_db_row_not_returned():
    """ON CONFLICT DO NOTHING with no RETURNING row (duplicate delivery) must not
    attempt a dual-write with a missing event_id."""
    mock_immudb = MagicMock()
    consumer, mock_conn = _make_consumer_with_fetchrow(None, immudb_service=mock_immudb)

    await consumer._write_audit({"event_type": "DOC_INGESTED", "tenant_id": "t-1"})

    mock_immudb.verified_set.assert_not_called()


# ── occurred_at parsing — asyncpg needs a real datetime, not an ISO str ─────

@pytest.mark.asyncio
async def test_write_audit_parses_naive_iso_occurred_at():
    import datetime
    consumer, mock_conn = _make_consumer_with_fetchrow({"event_id": "evt-1"})

    await consumer._write_audit({
        "event_type": "DOC_INGESTED", "tenant_id": "tenant-xyz",
        "occurred_at": "2026-07-18T17:08:13.124071",
    })

    occurred_arg = mock_conn.fetchrow.call_args.args[-1]
    assert isinstance(occurred_arg, datetime.datetime)
    assert occurred_arg.year == 2026 and occurred_arg.month == 7 and occurred_arg.day == 18


@pytest.mark.asyncio
async def test_write_audit_parses_timezone_aware_iso_occurred_at():
    """The exact format seen crashing in production: an offset-aware ISO string."""
    import datetime
    consumer, mock_conn = _make_consumer_with_fetchrow({"event_id": "evt-1"})

    await consumer._write_audit({
        "event_type": "TENANT_SUSPENDED", "tenant_id": "tenant-xyz",
        "occurred_at": "2026-07-18T17:08:13.124071+00:00",
    })

    occurred_arg = mock_conn.fetchrow.call_args.args[-1]
    assert isinstance(occurred_arg, datetime.datetime)
    assert occurred_arg.tzinfo is not None


@pytest.mark.asyncio
async def test_write_audit_falls_back_to_none_when_occurred_at_missing():
    """Missing occurred_at must bind None so SQL's COALESCE(..., NOW()) applies —
    never crash on absence."""
    consumer, mock_conn = _make_consumer_with_fetchrow({"event_id": "evt-1"})

    await consumer._write_audit({"event_type": "DOC_INGESTED", "tenant_id": "tenant-xyz"})

    occurred_arg = mock_conn.fetchrow.call_args.args[-1]
    assert occurred_arg is None


@pytest.mark.asyncio
async def test_write_audit_falls_back_to_none_when_occurred_at_unparseable():
    """A malformed timestamp must not crash the consumer — degrade to NOW()."""
    consumer, mock_conn = _make_consumer_with_fetchrow({"event_id": "evt-1"})

    await consumer._write_audit({
        "event_type": "DOC_INGESTED", "tenant_id": "tenant-xyz", "occurred_at": "not-a-date",
    })

    occurred_arg = mock_conn.fetchrow.call_args.args[-1]
    assert occurred_arg is None
