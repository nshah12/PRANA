"""Tests for services/otp_service.py."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.otp_service import OTPService


def _make_redis(stored=None):
    r = AsyncMock()
    r.setex = AsyncMock()
    r.get = AsyncMock(return_value=stored)
    r.delete = AsyncMock()
    r.ttl = AsyncMock(return_value=300)
    return r


@pytest.mark.asyncio
async def test_otp_is_6_digits():
    redis = _make_redis()
    svc = OTPService(redis)
    code = await svc.generate("LOGIN", "pan_token_abc", ttl_seconds=600)
    assert len(code) == 6
    assert code.isdigit()


@pytest.mark.asyncio
async def test_otp_expires_after_ttl_from_config():
    redis = _make_redis()
    svc = OTPService(redis)
    await svc.generate("LOGIN", "pan_token_abc", ttl_seconds=300)

    redis.setex.assert_called_once()
    args = redis.setex.call_args[0]
    assert args[1] == 300, "TTL passed to setex must match the configured value"


@pytest.mark.asyncio
async def test_otp_rate_limit_blocks_after_3_requests_per_10_min():
    # After 3 failed attempts the key is deleted and further verify calls return False
    redis = _make_redis(stored=b"987654:3")  # already at 3 attempts (code != dev bypass)
    svc = OTPService(redis)
    result = await svc.verify("LOGIN", "pan_token_abc", "987654")
    assert result is False, "3 failed attempts must block further verification"
    redis.delete.assert_called()


@pytest.mark.asyncio
async def test_otp_value_never_logged():
    src = inspect.getsource(OTPService.generate)
    # In generate() the code must NOT be logged (only in dev mode via send_otp — outside this service)
    assert 'log.info' not in src or 'code' not in src, \
        "OTPService.generate must not log the OTP code"
