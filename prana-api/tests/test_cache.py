"""Tests for lib/cache.py — server-side Redis cache with automatic invalidation.

Previously had zero test coverage (TDD-01 violation — lib/ is not in the exempt
list). Real behavior tests against a mocked Redis client, not source inspection.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from lib.cache import (
    cache_get, cache_set, cache_invalidate, cached,
    invalidate_tenants, invalidate_platform_config, invalidate_tenant_config,
)


def _mock_redis(get_return=None, keys_return=None, delete_return=0):
    r = AsyncMock()
    r.get = AsyncMock(return_value=get_return)
    r.setex = AsyncMock()
    r.keys = AsyncMock(return_value=keys_return or [])
    r.delete = AsyncMock(return_value=delete_return)
    return r


# ── cache_get ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_get_returns_none_on_miss():
    r = _mock_redis(get_return=None)
    with patch("lib.cache.get_redis", return_value=r):
        result = await cache_get("prana:tenants:global")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_returns_deserialized_value_on_hit():
    r = _mock_redis(get_return=json.dumps({"tenants": [1, 2, 3]}))
    with patch("lib.cache.get_redis", return_value=r):
        result = await cache_get("prana:tenants:global")
    assert result == {"tenants": [1, 2, 3]}


@pytest.mark.asyncio
async def test_cache_get_fails_open_on_redis_error():
    """Redis being down must never break the request — cache_get swallows and returns None."""
    r = AsyncMock()
    r.get = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("lib.cache.get_redis", return_value=r):
        result = await cache_get("prana:tenants:global")
    assert result is None


# ── cache_set ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_set_serializes_value_with_ttl():
    r = _mock_redis()
    with patch("lib.cache.get_redis", return_value=r):
        await cache_set("prana:tenants:global", {"a": 1}, ttl=120)
    r.setex.assert_awaited_once_with("prana:tenants:global", 120, json.dumps({"a": 1}, default=str))


@pytest.mark.asyncio
async def test_cache_set_defaults_to_60_second_ttl():
    r = _mock_redis()
    with patch("lib.cache.get_redis", return_value=r):
        await cache_set("prana:tenants:global", {"a": 1})
    assert r.setex.await_args.args[1] == 60


@pytest.mark.asyncio
async def test_cache_set_fails_open_on_redis_error():
    r = AsyncMock()
    r.setex = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("lib.cache.get_redis", return_value=r):
        await cache_set("prana:tenants:global", {"a": 1})  # must not raise


# ── cache_invalidate ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_invalidate_deletes_matching_keys():
    r = _mock_redis(keys_return=["prana:tenants:1", "prana:tenants:2"], delete_return=2)
    with patch("lib.cache.get_redis", return_value=r):
        count = await cache_invalidate("prana:tenants:*")
    assert count == 2
    r.delete.assert_awaited_once_with("prana:tenants:1", "prana:tenants:2")


@pytest.mark.asyncio
async def test_cache_invalidate_returns_zero_when_no_keys_match():
    r = _mock_redis(keys_return=[])
    with patch("lib.cache.get_redis", return_value=r):
        count = await cache_invalidate("prana:tenants:*")
    assert count == 0
    r.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_invalidate_fails_open_on_redis_error():
    r = AsyncMock()
    r.keys = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("lib.cache.get_redis", return_value=r):
        count = await cache_invalidate("prana:tenants:*")
    assert count == 0


# ── @cached decorator ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cached_decorator_returns_cached_value_without_calling_wrapped_fn():
    r = _mock_redis(get_return=json.dumps("cached-result"))
    calls = []

    @cached("tenants", ttl=60)
    async def handler():
        calls.append(1)
        return "fresh-result"

    with patch("lib.cache.get_redis", return_value=r):
        result = await handler()

    assert result == "cached-result"
    assert calls == []


@pytest.mark.asyncio
async def test_cached_decorator_calls_fn_and_populates_cache_on_miss():
    r = _mock_redis(get_return=None)

    @cached("tenants", ttl=60)
    async def handler():
        return {"count": 5}

    with patch("lib.cache.get_redis", return_value=r):
        result = await handler()

    assert result == {"count": 5}
    r.setex.assert_awaited_once_with("prana:tenants:global", 60, json.dumps({"count": 5}, default=str))


@pytest.mark.asyncio
async def test_cached_decorator_scopes_key_by_scope_arg():
    r = _mock_redis(get_return=None)

    @cached("tenant_config", ttl=60, scope_arg="tenant_id")
    async def handler(tenant_id):
        return {"tenant_id": tenant_id}

    with patch("lib.cache.get_redis", return_value=r):
        await handler(tenant_id="t-1")

    r.get.assert_awaited_once_with("prana:tenant_config:t-1")


# ── Convenience invalidation helpers ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_tenants_uses_tenants_wildcard_pattern():
    r = _mock_redis(keys_return=["prana:tenants:global"])
    with patch("lib.cache.get_redis", return_value=r):
        await invalidate_tenants()
    r.keys.assert_awaited_once_with("prana:tenants:*")


@pytest.mark.asyncio
async def test_invalidate_platform_config_uses_platform_config_wildcard_pattern():
    r = _mock_redis(keys_return=[])
    with patch("lib.cache.get_redis", return_value=r):
        await invalidate_platform_config()
    r.keys.assert_awaited_once_with("prana:platform_config:*")


@pytest.mark.asyncio
async def test_invalidate_tenant_config_scopes_to_single_tenant():
    r = _mock_redis(keys_return=["prana:tenant_config:t-1"])
    with patch("lib.cache.get_redis", return_value=r):
        await invalidate_tenant_config("t-1")
    r.keys.assert_awaited_once_with("prana:tenant_config:t-1")
