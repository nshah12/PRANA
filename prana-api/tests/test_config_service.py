"""Tests for services/config_service.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.config_service import ConfigService


def _make_redis():
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_tenant_config_overrides_platform_config():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"resolved_value": "42"})
    svc = ConfigService(db, _make_redis())

    val = await svc.get("otp_ttl_minutes", tenant_id="tenant-001")
    assert val == "42"


@pytest.mark.asyncio
async def test_missing_key_falls_back_to_platform_config():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"resolved_value": "600"})
    svc = ConfigService(db, _make_redis())

    val = await svc.get("otp_ttl_minutes", tenant_id="tenant-001")
    assert val == "600"


@pytest.mark.asyncio
async def test_get_int_returns_integer_not_string():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"resolved_value": "30"})
    svc = ConfigService(db, _make_redis())

    val = await svc.get_int("some_limit", tenant_id=None)
    assert isinstance(val, int)
    assert val == 30
