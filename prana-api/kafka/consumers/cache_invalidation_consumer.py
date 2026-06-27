"""
CacheInvalidationConsumer — prana.cache.invalidation

Runs on EVERY API pod (not just one). Each pod maintains its own Redis
connection and must invalidate keys when the source of truth changes.

Events handled:
  CONFIG_INVALIDATE          → DEL config:tenant:{tenant_id}:* or config:platform:{key}
  APIKEY_INVALIDATE          → DEL apikey:{key_hash}
  MANIFEST_INVALIDATE        → DEL tenant:{tenant_id}:manifest:{doc_type} + :all
  EMPLOYEE_PROFILE_INVALIDATE → DEL emp:profile:{employee_user_id}
  TENANT_INVALIDATE          → DEL tenant:{tenant_id}:profile + stats + manifests + config
  OA_PERMISSIONS_INVALIDATE  → DEL oa:profile:{oa_user_id} + oa:permissions:{id} + oa:elevation:{id}
  DROPDOWN_INVALIDATE        → DEL ref:{name}
  SESSION_INVALIDATE         → DEL session:{session_id} (force re-auth)

Design: auto_commit=True, auto_offset_reset="latest".
Cache invalidation is best-effort and real-time only — replaying history would
thrash the cache on pod restarts. Worst case: stale cache expires via TTL.
"""
import json
import logging

from aiokafka import AIOKafkaConsumer

from config import Settings
from services.cache_service import CacheService

log = logging.getLogger(__name__)

GROUP_ID = "prana-cache-invalidation-{pod_id}"   # unique per pod — each pod gets all messages


class CacheInvalidationConsumer:
    def __init__(self, settings: Settings, redis, pod_id: str = "default") -> None:
        self._cache = CacheService(redis)
        self._consumer = AIOKafkaConsumer(
            "prana.cache.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("CacheInvalidationConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("CacheInvalidationConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: str, event: dict) -> None:
        if etype == "CONFIG_INVALIDATE":
            tenant_id = event.get("tenant_id")
            key       = event.get("config_key")
            if tenant_id and key:
                await self._cache._del(f"config:tenant:{tenant_id}:{key}")
            await self._cache.invalidate_config(tenant_id)

        elif etype == "APIKEY_INVALIDATE":
            key_hash = event.get("key_hash")
            if key_hash:
                await self._cache.invalidate_api_key(key_hash)

        elif etype == "MANIFEST_INVALIDATE":
            tenant_id = event.get("tenant_id")
            doc_type  = event.get("doc_type")
            if tenant_id:
                await self._cache.invalidate_manifests(tenant_id, doc_type)

        elif etype == "EMPLOYEE_PROFILE_INVALIDATE":
            emp_id = event.get("employee_user_id")
            if emp_id:
                await self._cache.invalidate_emp_profile(emp_id)

        elif etype == "TENANT_INVALIDATE":
            tenant_id = event.get("tenant_id")
            if tenant_id:
                await self._cache.invalidate_tenant(tenant_id)

        elif etype == "OA_PERMISSIONS_INVALIDATE":
            oa_user_id = event.get("oa_user_id")
            if oa_user_id:
                await self._cache.invalidate_oa_user(oa_user_id)

        elif etype == "DROPDOWN_INVALIDATE":
            name = event.get("name")
            if name:
                await self._cache.invalidate_dropdown(name)
            else:
                # Invalidate all dropdowns — rare (e.g. new doc type added)
                for dropdown in ("doc_types", "states:IN", "industries", "banks",
                                 "statutory_acts", "exception_types", "oa_roles",
                                 "notification_templates", "labour_categories"):
                    await self._cache.invalidate_dropdown(dropdown)

        elif etype == "SESSION_INVALIDATE":
            session_id = event.get("session_id")
            if session_id and self._cache._r:
                await self._cache._del(f"session:{session_id}")

        else:
            log.debug("CacheInvalidationConsumer: unhandled event_type=%s", etype)
