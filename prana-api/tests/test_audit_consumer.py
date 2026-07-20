"""
Tests for kafka/consumers/audit_consumer.py.

Covers: _write_audit() must parse occurred_at from the Kafka event's ISO
string into a real datetime before binding it to the $8::timestamptz
parameter. asyncpg's binary protocol encodes bound parameters based on the
prepared statement's inferred type (timestamptz here) - the SQL-side
`::timestamptz` cast does NOT make asyncpg accept a plain str for that
parameter, so passing the raw string crashes with asyncpg.exceptions.DataError
the moment any HTTP handler in this app publishes an ISO string occurred_at
(which is how every kafka.publish() call in the codebase does it).
"""
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from kafka.consumers.audit_consumer import AuditConsumer


def _make_consumer():
    settings = MagicMock()
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    consumer = AuditConsumer(settings, pool)
    return consumer, conn


@pytest.mark.asyncio
async def test_write_audit_parses_naive_iso_occurred_at():
    consumer, conn = _make_consumer()
    event = {
        "event_type": "DOC_INGESTED",
        "tenant_id": "tenant-xyz",
        "occurred_at": "2026-07-18T17:08:13.124071",
    }

    await consumer._write_audit(event)

    occurred_arg = conn.execute.call_args.args[-1]
    assert isinstance(occurred_arg, datetime.datetime)
    assert occurred_arg.year == 2026 and occurred_arg.month == 7 and occurred_arg.day == 18


@pytest.mark.asyncio
async def test_write_audit_parses_timezone_aware_iso_occurred_at():
    """The exact format seen crashing in production: an offset-aware ISO string."""
    consumer, conn = _make_consumer()
    event = {
        "event_type": "TENANT_SUSPENDED",
        "tenant_id": "tenant-xyz",
        "occurred_at": "2026-07-18T17:08:13.124071+00:00",
    }

    await consumer._write_audit(event)

    occurred_arg = conn.execute.call_args.args[-1]
    assert isinstance(occurred_arg, datetime.datetime)
    assert occurred_arg.tzinfo is not None


@pytest.mark.asyncio
async def test_write_audit_falls_back_to_none_when_occurred_at_missing():
    """Missing occurred_at must bind None so SQL's COALESCE(..., NOW()) applies —
    never crash on absence."""
    consumer, conn = _make_consumer()
    event = {"event_type": "DOC_INGESTED", "tenant_id": "tenant-xyz"}

    await consumer._write_audit(event)

    occurred_arg = conn.execute.call_args.args[-1]
    assert occurred_arg is None


@pytest.mark.asyncio
async def test_write_audit_falls_back_to_none_when_occurred_at_unparseable():
    """A malformed timestamp must not crash the consumer — degrade to NOW()."""
    consumer, conn = _make_consumer()
    event = {"event_type": "DOC_INGESTED", "tenant_id": "tenant-xyz", "occurred_at": "not-a-date"}

    await consumer._write_audit(event)

    occurred_arg = conn.execute.call_args.args[-1]
    assert occurred_arg is None
