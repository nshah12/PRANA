"""
Tests for CacheService — Redis wrapper for config, API keys, rate limiting, locks, dropdowns.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _svc(redis=None):
    from services.cache_service import CacheService
    return CacheService(redis)


# ── None-safe (Redis unavailable) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_none_when_redis_unavailable():
    svc = _svc(redis=None)
    assert await svc.get_platform_config("any_key") is None
    assert await svc.get_api_key("hash") is None
    assert await svc.get_tenant_config("t1", "k") is None


@pytest.mark.asyncio
async def test_set_is_noop_when_redis_unavailable():
    svc = _svc(redis=None)
    await svc.set_platform_config("key", "value")  # must not raise


@pytest.mark.asyncio
async def test_lock_returns_true_when_redis_unavailable():
    """Fail open — no Redis in dev → always allow proceeding."""
    svc = _svc(redis=None)
    assert await svc.acquire_ingest_lock("doc-001") is True


@pytest.mark.asyncio
async def test_rate_limit_returns_zero_when_redis_unavailable():
    svc = _svc(redis=None)
    assert await svc.check_otp_rate("+919000000001") == 0


# ── Config cache ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_platform_config_set_then_get():
    mock_redis = AsyncMock()
    import json
    stored = {}
    async def _set(key, value, ex): stored[key] = value
    async def _get(key): return stored.get(key)
    mock_redis.set = _set
    mock_redis.get = _get

    svc = _svc(mock_redis)
    await svc.set_platform_config("otp_ttl_minutes", "10")
    val = await svc.get_platform_config("otp_ttl_minutes")
    assert val == "10"


@pytest.mark.asyncio
async def test_tenant_config_all_roundtrip():
    mock_redis = AsyncMock()
    import json
    stored = {}
    async def _set(key, value, ex): stored[key] = value
    async def _get(key): raw = stored.get(key); return raw
    mock_redis.set = _set
    mock_redis.get = _get

    svc = _svc(mock_redis)
    cfg = {"otp_ttl_minutes": 10, "share_max_active": 5}
    await svc.set_tenant_config_all("tenant-001", cfg)
    result = await svc.get_tenant_config_all("tenant-001")
    assert result == cfg


# ── API key cache ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_key_cache_hit():
    mock_redis = AsyncMock()
    import json
    key_row = {"tenant_id": "t1", "status": "ACTIVE", "api_version": "v1"}
    stored = {f"apikey:abc123": json.dumps(key_row)}
    mock_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

    svc = _svc(mock_redis)
    result = await svc.get_api_key("abc123")
    assert result == key_row
    mock_redis.get.assert_called_once_with("apikey:abc123")


@pytest.mark.asyncio
async def test_api_key_invalidate_calls_del():
    mock_redis = AsyncMock()
    svc = _svc(mock_redis)
    await svc.invalidate_api_key("abc123")
    mock_redis.delete.assert_called_once_with("apikey:abc123")


# ── Manifest cache ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manifest_invalidation_clears_all_and_specific():
    mock_redis = AsyncMock()
    svc = _svc(mock_redis)
    await svc.invalidate_manifests("tenant-001", "SALARY_SLIP")
    # Should delete both the :all key and the specific doc_type key
    deleted_keys = {call.args[0] for call in mock_redis.delete.call_args_list}
    assert "tenant:tenant-001:manifests:all" in deleted_keys
    assert "tenant:tenant-001:manifest:SALARY_SLIP" in deleted_keys


# ── Rate limiting ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_otp_rate_limit_increments():
    mock_redis = AsyncMock()
    counter = [0]
    async def _incr(key): counter[0] += 1; return counter[0]
    mock_redis.incr = _incr
    mock_redis.expire = AsyncMock()

    svc = _svc(mock_redis)
    c1 = await svc.check_otp_rate("+919000000001")
    c2 = await svc.check_otp_rate("+919000000001")
    assert c1 == 1
    assert c2 == 2


@pytest.mark.asyncio
async def test_otp_rate_limit_sets_ttl_on_first_call():
    mock_redis = AsyncMock()
    counter = [0]
    async def _incr(key): counter[0] += 1; return counter[0]
    mock_redis.incr = _incr
    mock_redis.expire = AsyncMock()

    svc = _svc(mock_redis)
    from services.cache_service import TTL_RL_OTP
    await svc.check_otp_rate("+919000000001")
    mock_redis.expire.assert_called_once()
    _, ttl = mock_redis.expire.call_args[0]
    assert ttl == TTL_RL_OTP


# ── Distributed locks ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acquire_lock_returns_true_on_success():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)  # SET NX succeeded

    svc = _svc(mock_redis)
    result = await svc.acquire_ingest_lock("doc-001")
    assert result is True
    mock_redis.set.assert_called_once()
    args = mock_redis.set.call_args
    assert args[1]["nx"] is True
    assert args[0][0] == "lock:ingest:doc-001"


@pytest.mark.asyncio
async def test_acquire_lock_returns_false_when_already_held():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)  # NX failed — key exists

    svc = _svc(mock_redis)
    result = await svc.acquire_ingest_lock("doc-001")
    assert result is False


# ── Consent state ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consent_withdrawal_sets_flag():
    mock_redis = AsyncMock()
    import json
    stored = {}
    async def _set(key, value, ex): stored[key] = value
    async def _get(key): return stored.get(key)
    mock_redis.set = _set
    mock_redis.get = _get

    svc = _svc(mock_redis)
    await svc.withdraw_consent("emp-001")
    withdrawn = await svc.is_consent_withdrawn("emp-001")
    assert withdrawn is True


# ── Dropdown cache ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dropdown_cache_roundtrip():
    mock_redis = AsyncMock()
    import json
    stored = {}
    async def _set(key, value, ex): stored[key] = value
    async def _get(key): return stored.get(key)
    mock_redis.set = _set
    mock_redis.get = _get

    svc = _svc(mock_redis)
    items = [{"value": "SALARY_SLIP", "label": "Salary Slip"}, {"value": "FORM_16", "label": "Form 16"}]
    await svc.set_dropdown("doc_types", items)
    result = await svc.get_dropdown("doc_types")
    assert result == items


# ── No raw PAN / salary in cache ─────────────────────────────────────────────

def test_cache_service_has_no_salary_or_pan_methods():
    """CacheService must not expose methods that cache raw salary or PAN values."""
    from services.cache_service import CacheService
    import inspect
    src = inspect.getsource(CacheService)
    assert "salary" not in src.lower(), "CacheService must not cache raw salary figures"
    # pan_token is allowed (HMAC output), but not raw PAN
    assert "raw_pan" not in src and '"pan"' not in src, \
        "CacheService must not cache raw PAN — only pan_token (HMAC output)"
