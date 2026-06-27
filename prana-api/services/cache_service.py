"""
CacheService — Redis-backed cache for all hot-read, cold-write data.

Replaces synchronous DB fetches for:
  - platform_config / tenant_config  (read by every Temporal activity)
  - API key validation               (read on every HRMS ingest request)
  - Dropdowns / reference data       (doc types, states, industries, roles...)
  - Rate limiting counters           (OTP, login, ingest, share, export)
  - Distributed locks                (ingest dedup, erasure, KEK rotation)
  - Employee & OA user profiles      (mobile vault, portal OA screens)
  - Manifests for AUTO_DETECT        (prana-ai calls internal API)

Invalidation: publish CONFIG_INVALIDATE / APIKEY_INVALIDATE etc. to
prana.cache.invalidation → CacheInvalidationConsumer DELs the key on all pods.
"""
import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── TTLs (seconds) ────────────────────────────────────────────────────────────
TTL_CONFIG          = 900    # 15 min — platform/tenant config
TTL_APIKEY          = 300    # 5 min  — API key rows
TTL_DROPDOWN        = 86400  # 24 h   — static reference data
TTL_MANIFEST        = 1800   # 30 min — doc type manifests
TTL_TENANT_PROFILE  = 3600   # 1 h    — tenant metadata
TTL_TENANT_STATS    = 300    # 5 min  — doc/emp counts
TTL_EMP_PROFILE     = 1800   # 30 min — employee profile
TTL_OA_PROFILE      = 1800   # 30 min — OA user profile
TTL_OA_PERMS        = 900    # 15 min — effective permissions
TTL_CONSENT         = 1800   # 30 min — consent state per purpose
TTL_PIPELINE_STATUS = 86400  # 24 h   — current pipeline stage
TTL_ANALYTICS       = 300    # 5 min  — analytics counters

# Rate-limit windows
TTL_RL_OTP          = 600    # 10 min
TTL_RL_LOGIN        = 900    # 15 min
TTL_RL_INGEST       = 60     # 1 min
TTL_RL_DAILY        = 86400  # 24 h

# Lock TTLs — NX ensures only first caller wins
TTL_LOCK_INGEST     = 60     # 1 min
TTL_LOCK_ERASURE    = 300    # 5 min
TTL_LOCK_KEK        = 600    # 10 min


class CacheService:
    """
    Thin async wrapper around redis.asyncio.Redis.
    All methods are safe to call when redis is None (returns None / False / 0).
    """

    def __init__(self, redis) -> None:
        self._r = redis

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_json(self, key: str) -> Optional[Any]:
        if not self._r:
            return None
        try:
            raw = await self._r.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            log.warning("Redis GET failed key=%s", key)
            return None

    async def _set_json(self, key: str, value: Any, ttl: int) -> None:
        if not self._r:
            return
        try:
            await self._r.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            log.warning("Redis SET failed key=%s", key)

    async def _del(self, *keys: str) -> None:
        if not self._r or not keys:
            return
        try:
            await self._r.delete(*keys)
        except Exception:
            log.warning("Redis DEL failed keys=%s", keys)

    # ── Config ────────────────────────────────────────────────────────────────

    async def get_platform_config(self, key: str) -> Optional[str]:
        return await self._get_json(f"config:platform:{key}")

    async def set_platform_config(self, key: str, value: str) -> None:
        await self._set_json(f"config:platform:{key}", value, TTL_CONFIG)

    async def get_tenant_config(self, tenant_id: str, key: str) -> Optional[str]:
        return await self._get_json(f"config:tenant:{tenant_id}:{key}")

    async def set_tenant_config(self, tenant_id: str, key: str, value: str) -> None:
        await self._set_json(f"config:tenant:{tenant_id}:{key}", value, TTL_CONFIG)

    async def get_tenant_config_all(self, tenant_id: str) -> Optional[dict]:
        return await self._get_json(f"config:tenant:{tenant_id}:all")

    async def set_tenant_config_all(self, tenant_id: str, config: dict) -> None:
        await self._set_json(f"config:tenant:{tenant_id}:all", config, TTL_CONFIG)

    async def invalidate_config(self, tenant_id: Optional[str] = None) -> None:
        if tenant_id:
            # Delete all keys matching config:tenant:{id}:*
            # Redis Cluster: use SCAN per shard (no KEYS command in cluster mode)
            await self._del(f"config:tenant:{tenant_id}:all")
        else:
            # Platform config change — rare, acceptable to just let TTL expire
            # or publish DROPDOWN_INVALIDATE for immediate effect
            pass

    # ── API Keys ──────────────────────────────────────────────────────────────

    async def get_api_key(self, key_hash: str) -> Optional[dict]:
        return await self._get_json(f"apikey:{key_hash}")

    async def set_api_key(self, key_hash: str, row: dict) -> None:
        await self._set_json(f"apikey:{key_hash}", row, TTL_APIKEY)

    async def invalidate_api_key(self, key_hash: str) -> None:
        await self._del(f"apikey:{key_hash}")

    # ── Dropdowns / reference data ────────────────────────────────────────────

    async def get_dropdown(self, name: str) -> Optional[list]:
        return await self._get_json(f"ref:{name}")

    async def set_dropdown(self, name: str, items: list) -> None:
        await self._set_json(f"ref:{name}", items, TTL_DROPDOWN)

    async def invalidate_dropdown(self, name: str) -> None:
        await self._del(f"ref:{name}")

    # ── Manifests ────────────────────────────────────────────────────────────

    async def get_manifest(self, tenant_id: str, doc_type: str) -> Optional[dict]:
        return await self._get_json(f"tenant:{tenant_id}:manifest:{doc_type}")

    async def set_manifest(self, tenant_id: str, doc_type: str, manifest: dict) -> None:
        await self._set_json(f"tenant:{tenant_id}:manifest:{doc_type}", manifest, TTL_MANIFEST)

    async def get_all_manifests(self, tenant_id: str) -> Optional[list]:
        return await self._get_json(f"tenant:{tenant_id}:manifests:all")

    async def set_all_manifests(self, tenant_id: str, manifests: list) -> None:
        await self._set_json(f"tenant:{tenant_id}:manifests:all", manifests, TTL_MANIFEST)

    async def invalidate_manifests(self, tenant_id: str, doc_type: Optional[str] = None) -> None:
        await self._del(f"tenant:{tenant_id}:manifests:all")
        if doc_type:
            await self._del(f"tenant:{tenant_id}:manifest:{doc_type}")

    # ── Tenant profile ────────────────────────────────────────────────────────

    async def get_tenant_profile(self, tenant_id: str) -> Optional[dict]:
        return await self._get_json(f"tenant:{tenant_id}:profile")

    async def set_tenant_profile(self, tenant_id: str, profile: dict) -> None:
        await self._set_json(f"tenant:{tenant_id}:profile", profile, TTL_TENANT_PROFILE)

    async def get_tenant_stats(self, tenant_id: str) -> Optional[dict]:
        return await self._get_json(f"tenant:{tenant_id}:stats")

    async def set_tenant_stats(self, tenant_id: str, stats: dict) -> None:
        await self._set_json(f"tenant:{tenant_id}:stats", stats, TTL_TENANT_STATS)

    async def invalidate_tenant(self, tenant_id: str) -> None:
        await self._del(
            f"tenant:{tenant_id}:profile",
            f"tenant:{tenant_id}:stats",
            f"tenant:{tenant_id}:manifests:all",
            f"config:tenant:{tenant_id}:all",
        )

    # ── Employee profile ──────────────────────────────────────────────────────

    async def get_emp_profile(self, employee_user_id: str) -> Optional[dict]:
        return await self._get_json(f"emp:profile:{employee_user_id}")

    async def set_emp_profile(self, employee_user_id: str, profile: dict) -> None:
        await self._set_json(f"emp:profile:{employee_user_id}", profile, TTL_EMP_PROFILE)

    async def invalidate_emp_profile(self, employee_user_id: str) -> None:
        await self._del(f"emp:profile:{employee_user_id}")

    # ── OA user profile & permissions ────────────────────────────────────────

    async def get_oa_profile(self, oa_user_id: str) -> Optional[dict]:
        return await self._get_json(f"oa:profile:{oa_user_id}")

    async def set_oa_profile(self, oa_user_id: str, profile: dict) -> None:
        await self._set_json(f"oa:profile:{oa_user_id}", profile, TTL_OA_PROFILE)

    async def get_oa_permissions(self, oa_user_id: str) -> Optional[dict]:
        return await self._get_json(f"oa:permissions:{oa_user_id}")

    async def set_oa_permissions(self, oa_user_id: str, perms: dict) -> None:
        await self._set_json(f"oa:permissions:{oa_user_id}", perms, TTL_OA_PERMS)

    async def get_oa_elevation(self, oa_user_id: str) -> Optional[dict]:
        return await self._get_json(f"oa:elevation:{oa_user_id}")

    async def set_oa_elevation(self, oa_user_id: str, elevation: dict, ttl_seconds: int) -> None:
        await self._set_json(f"oa:elevation:{oa_user_id}", elevation, ttl_seconds)

    async def invalidate_oa_user(self, oa_user_id: str) -> None:
        await self._del(
            f"oa:profile:{oa_user_id}",
            f"oa:permissions:{oa_user_id}",
            f"oa:elevation:{oa_user_id}",
        )

    # ── Consent state ────────────────────────────────────────────────────────

    async def get_consent(self, employee_user_id: str, purpose: str) -> Optional[bool]:
        val = await self._get_json(f"consent:{employee_user_id}:{purpose}")
        return val  # True = granted, False = withdrawn, None = unknown (check DB)

    async def set_consent(self, employee_user_id: str, purpose: str, granted: bool) -> None:
        await self._set_json(f"consent:{employee_user_id}:{purpose}", granted, TTL_CONSENT)

    async def withdraw_consent(self, employee_user_id: str) -> None:
        """Withdrawal is immediate — set flag for fast stop-processing check."""
        await self._set_json(f"consent:withdrawn:{employee_user_id}", True, TTL_CONSENT)

    async def is_consent_withdrawn(self, employee_user_id: str) -> bool:
        val = await self._get_json(f"consent:withdrawn:{employee_user_id}")
        return bool(val)

    # ── Pipeline status ──────────────────────────────────────────────────────

    async def get_pipeline_status(self, document_id: str) -> Optional[str]:
        return await self._get_json(f"pipeline:status:{document_id}")

    async def set_pipeline_status(self, document_id: str, stage: str) -> None:
        await self._set_json(f"pipeline:status:{document_id}", stage, TTL_PIPELINE_STATUS)

    # ── Rate limiting ────────────────────────────────────────────────────────

    async def incr_rate_limit(self, key: str, ttl: int) -> int:
        """Increment counter. Sets TTL on first call. Returns new count."""
        if not self._r:
            return 0
        try:
            count = await self._r.incr(key)
            if count == 1:
                await self._r.expire(key, ttl)
            return count
        except Exception:
            log.warning("Redis INCR failed key=%s", key)
            return 0

    async def check_otp_rate(self, phone: str) -> int:
        return await self.incr_rate_limit(f"rl:otp:{phone}", TTL_RL_OTP)

    async def check_login_rate(self, ip: str) -> int:
        return await self.incr_rate_limit(f"rl:login:{ip}", TTL_RL_LOGIN)

    async def check_ingest_rate(self, api_key_id: str) -> int:
        import time
        window = int(time.time()) // 60
        return await self.incr_rate_limit(f"rl:ingest:{api_key_id}:{window}", TTL_RL_INGEST)

    async def check_share_rate(self, employee_user_id: str) -> int:
        return await self.incr_rate_limit(f"rl:share:{employee_user_id}:daily", TTL_RL_DAILY)

    async def check_export_rate(self, employee_user_id: str) -> int:
        return await self.incr_rate_limit(f"rl:export:{employee_user_id}:daily", TTL_RL_DAILY)

    # ── Distributed locks ────────────────────────────────────────────────────

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        """SET key 1 NX EX ttl — returns True if lock acquired."""
        if not self._r:
            return True  # no Redis in dev → always proceed
        try:
            result = await self._r.set(key, "1", nx=True, ex=ttl)
            return result is not None
        except Exception:
            log.warning("Redis lock acquire failed key=%s", key)
            return True  # fail open — better than deadlock

    async def release_lock(self, key: str) -> None:
        await self._del(key)

    async def acquire_ingest_lock(self, document_id: str) -> bool:
        return await self.acquire_lock(f"lock:ingest:{document_id}", TTL_LOCK_INGEST)

    async def acquire_erasure_lock(self, employee_user_id: str) -> bool:
        return await self.acquire_lock(f"lock:erasure:{employee_user_id}", TTL_LOCK_ERASURE)

    async def acquire_kek_rotation_lock(self, tenant_id: str) -> bool:
        return await self.acquire_lock(f"lock:kek_rotation:{tenant_id}", TTL_LOCK_KEK)

    # ── Analytics counters ───────────────────────────────────────────────────

    async def incr_pipeline_throughput(self) -> None:
        """Increment hourly document processing counter."""
        if not self._r:
            return
        import time
        hour_key = f"analytics:throughput:{int(time.time()) // 3600}"
        try:
            count = await self._r.incr(hour_key)
            if count == 1:
                await self._r.expire(hour_key, 7200)  # 2h
        except Exception:
            pass

    async def get_pipeline_throughput(self) -> int:
        import time
        hour_key = f"analytics:throughput:{int(time.time()) // 3600}"
        val = await self._get_json(hour_key)
        return int(val) if val else 0
