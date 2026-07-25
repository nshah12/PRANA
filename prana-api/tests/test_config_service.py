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


@pytest.mark.asyncio
async def test_invalidate_all_deletes_every_cached_copy_of_key():
    """A platform-default edit (e.g. PA changing whatsapp_vendor_chain) must
    clear not just cfg:platform:{key} but every tenant's own cached copy of
    the resolved fallback value — each tenant caches under its OWN cache_key
    even when the value it got was the platform default, per get()'s
    cache_key = f"cfg:{tenant_id or 'platform'}:{key}". A single invalidate()
    call only clears the platform key, leaving every tenant's fallback copy
    stale for up to cache_ttl. Found via a real live run 2026-07-24 — see
    services/communication_settings_service.py's update_vendor_chain()."""
    db = AsyncMock()

    async def fake_scan_iter(match):
        assert match == "cfg:*:whatsapp_vendor_chain"
        for key in [b"cfg:platform:whatsapp_vendor_chain",
                    b"cfg:tenant-a:whatsapp_vendor_chain",
                    b"cfg:tenant-b:whatsapp_vendor_chain"]:
            yield key

    redis_client = MagicMock()
    redis_client.scan_iter = fake_scan_iter
    redis_client.delete = AsyncMock()
    svc = ConfigService(db, redis_client)

    await svc.invalidate_all("whatsapp_vendor_chain")

    redis_client.delete.assert_awaited_once_with(
        b"cfg:platform:whatsapp_vendor_chain",
        b"cfg:tenant-a:whatsapp_vendor_chain",
        b"cfg:tenant-b:whatsapp_vendor_chain",
    )


@pytest.mark.asyncio
async def test_invalidate_all_no_op_when_nothing_cached():
    db = AsyncMock()

    async def empty_scan_iter(match):
        return
        yield  # pragma: no cover — makes this an async generator

    redis_client = MagicMock()
    redis_client.scan_iter = empty_scan_iter
    redis_client.delete = AsyncMock()
    svc = ConfigService(db, redis_client)

    await svc.invalidate_all("whatsapp_vendor_chain")

    redis_client.delete.assert_not_awaited()
