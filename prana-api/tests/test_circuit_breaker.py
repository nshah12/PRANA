"""Tests for services/circuit_breaker.py.

RED first: CircuitBreaker doesn't exist yet — these fail on import.
Real invocation tests against mocked Redis + ConfigService, not source
inspection (see prana-docs memory "Verify SDK + Real Tests" lesson).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.circuit_breaker import CircuitBreaker


def _make_redis():
    r = MagicMock()
    r.exists = AsyncMock(return_value=0)
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    return r


def _make_config(threshold: int = 5, open_seconds: int = 60):
    cfg = AsyncMock()

    async def _get_int(key, tenant_id=None):
        if "threshold" in key:
            return threshold
        if "open_seconds" in key:
            return open_seconds
        return None

    cfg.get_int = AsyncMock(side_effect=_get_int)
    return cfg


@pytest.mark.asyncio
async def test_is_open_false_when_no_open_key_in_redis():
    redis = _make_redis()
    redis.exists.return_value = 0
    breaker = CircuitBreaker(redis, _make_config())

    assert await breaker.is_open("email", "ses") is False
    redis.exists.assert_called_once_with("circuit:email:ses:open")


@pytest.mark.asyncio
async def test_is_open_true_when_open_key_present():
    redis = _make_redis()
    redis.exists.return_value = 1
    breaker = CircuitBreaker(redis, _make_config())

    assert await breaker.is_open("sms", "aws") is True


@pytest.mark.asyncio
async def test_record_failure_below_threshold_does_not_open_circuit():
    redis = _make_redis()
    redis.incr.return_value = 3   # below threshold of 5
    breaker = CircuitBreaker(redis, _make_config(threshold=5))

    await breaker.record_failure("sms", "exotel")

    redis.incr.assert_called_once_with("circuit:sms:exotel:failures")
    redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_record_failure_at_threshold_opens_circuit():
    redis = _make_redis()
    redis.incr.return_value = 5   # hits threshold of 5
    breaker = CircuitBreaker(redis, _make_config(threshold=5, open_seconds=60))

    await breaker.record_failure("sms", "exotel")

    redis.setex.assert_called_once_with("circuit:sms:exotel:open", 60, "1")
    redis.delete.assert_called_once_with("circuit:sms:exotel:failures")


@pytest.mark.asyncio
async def test_record_failure_first_call_sets_expiry_on_counter():
    redis = _make_redis()
    redis.incr.return_value = 1
    breaker = CircuitBreaker(redis, _make_config(threshold=5, open_seconds=60))

    await breaker.record_failure("email", "ses")

    redis.expire.assert_called_once_with("circuit:email:ses:failures", 60)


@pytest.mark.asyncio
async def test_record_failure_reads_threshold_from_config_not_hardcoded():
    """Different tenants can have different thresholds — must come from
    ConfigService (tenant->platform resolution), never a literal in code."""
    redis = _make_redis()
    redis.incr.return_value = 2
    config = _make_config(threshold=2)
    breaker = CircuitBreaker(redis, config)

    await breaker.record_failure("ivr", "ozonetel", tenant_id="tenant-001")

    config.get_int.assert_any_call("comm_circuit_breaker_failure_threshold", "tenant-001")
    redis.setex.assert_called_once()   # threshold=2 reached on 2nd failure


@pytest.mark.asyncio
async def test_record_success_clears_both_keys():
    redis = _make_redis()
    breaker = CircuitBreaker(redis, _make_config())

    await breaker.record_success("whatsapp", "waba")

    redis.delete.assert_any_call("circuit:whatsapp:waba:failures")
    redis.delete.assert_any_call("circuit:whatsapp:waba:open")


@pytest.mark.asyncio
async def test_missing_config_falls_back_to_safe_defaults():
    """If comm_circuit_breaker_* keys are somehow unseeded, the breaker must
    still function (fail-safe defaults), not crash."""
    redis = _make_redis()
    redis.incr.return_value = 5
    config = AsyncMock()
    config.get_int = AsyncMock(return_value=None)   # unseeded
    breaker = CircuitBreaker(redis, config)

    await breaker.record_failure("email", "ses")   # must not raise
    redis.setex.assert_called_once_with("circuit:email:ses:open", 60, "1")
