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


@pytest.mark.asyncio
async def test_get_list_decodes_json_array():
    """Vendor chains (sms_vendor_chain, email_vendor_chain, etc.) are stored as a
    JSON array string in config_value (value_type='STRING') — no schema change,
    no new config-resolution mechanism, just JSON-decoding the existing get()."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"resolved_value": '["aws", "exotel", "msg91"]'})
    svc = ConfigService(db, _make_redis())

    val = await svc.get_list("sms_vendor_chain", tenant_id="tenant-001")
    assert val == ["aws", "exotel", "msg91"]


@pytest.mark.asyncio
async def test_get_list_returns_none_when_key_missing():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = ConfigService(db, _make_redis())

    val = await svc.get_list("nonexistent_key", tenant_id=None)
    assert val is None


@pytest.mark.asyncio
async def test_get_list_tenant_override_takes_precedence():
    """Confirms get_list rides the same tenant→platform resolution as get() —
    no separate mechanism for list-shaped config."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"resolved_value": '["msg91", "exotel"]'})
    svc = ConfigService(db, _make_redis())

    val = await svc.get_list("sms_vendor_chain", tenant_id="tenant-with-override")
    assert val == ["msg91", "exotel"]
    call_args = db.fetchrow.call_args[0]
    assert "tenant_config" in call_args[0]
