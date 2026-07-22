"""Tests for kafka/error_capture.py — record_consumer_error()."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from kafka.error_capture import record_consumer_error


def _boom() -> Exception:
    try:
        raise RuntimeError("consumer dispatch failed")
    except RuntimeError as e:
        return e


@pytest.mark.asyncio
async def test_records_via_error_observability_service_when_pool_present():
    mock_db = AsyncMock()
    mock_db.fetchrow = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock()
    db_pool = MagicMock()
    db_pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    ))

    await record_consumer_error(
        db_pool, consumer_name="NotifConsumer", exc=_boom(),
        event_type="ANOMALY_DETECTED", event_id="evt-1",
    )

    insert_calls = [c for c in mock_db.execute.call_args_list if "INSERT INTO error_event" in c.args[0]]
    assert len(insert_calls) == 1
    assert "NotifConsumer" in insert_calls[0].args
    assert "evt-1" in insert_calls[0].args


@pytest.mark.asyncio
async def test_no_op_when_db_pool_is_none():
    """Redis/Temporal-only consumers (no DB) must not crash."""
    await record_consumer_error(None, consumer_name="SSEFanoutConsumer", exc=_boom())


@pytest.mark.asyncio
async def test_never_raises_even_if_recording_itself_fails():
    db_pool = MagicMock()
    db_pool.acquire = MagicMock(side_effect=RuntimeError("pool exhausted"))

    await record_consumer_error(db_pool, consumer_name="AuthConsumer", exc=_boom())
    # No exception propagated — test passes simply by not raising.
