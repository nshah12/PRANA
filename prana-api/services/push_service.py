"""
Push notifications via Expo's push service — Communication Hub channel
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md). Expo is the only realistic
provider for an Expo SDK 56 app (no FCM/APNs credentials anywhere in this
codebase) — single-vendor chain for v1, but still goes through the same
config-driven vendor-chain + circuit-breaker shape as every other channel
adapter, matching services/whatsapp_service.py's stated reasoning (a second
vendor can be added later by extending push_vendor_chain and _dispatch — no
caller changes required).

Dev mode (settings.push_provider="dev"): logs to console, bypasses the
vendor chain entirely — same convention as every other channel adapter.

Expo's push API returns per-message errors inside a 200 response body (not
an HTTP error status) — DeviceNotRegistered is the one PushConsumer must
detect to clear the dead token from device_credential.push_token.
"""
import logging
from typing import Optional

import httpx

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService

log = logging.getLogger(__name__)

CHANNEL = "push"
_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushService:
    def __init__(self, settings: Settings, config: ConfigService, breaker: CircuitBreaker) -> None:
        self._settings = settings
        self._config = config
        self._breaker = breaker

    async def send(
        self, *, to: str, title: str, body: str,
        data: Optional[dict] = None, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if getattr(self._settings, "push_provider", "dev") == "dev":
            log.info("[DEV PUSH] to=%s title=%s", to, title)
            return True, None

        chain = await self._config.get_list(f"{CHANNEL}_vendor_chain", tenant_id)
        if not chain:
            log.error("No %s_vendor_chain configured — cannot send push to=%s", CHANNEL, to)
            return False, "no push vendor chain configured"

        last_error: Optional[str] = None
        for vendor in chain:
            if await self._breaker.is_open(CHANNEL, vendor):
                log.warning("Circuit open for push vendor=%s — skipping", vendor)
                continue
            sent, error = await self._dispatch(vendor, to, title, body, data)
            if sent:
                await self._breaker.record_success(CHANNEL, vendor)
                return True, None
            last_error = error
            await self._breaker.record_failure(CHANNEL, vendor, tenant_id)
        return False, last_error or "all push vendors in chain exhausted"

    async def _dispatch(
        self, vendor: str, to: str, title: str, body: str, data: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        if vendor == "expo":
            return await self._expo(to, title, body, data)
        log.warning("Unknown push vendor %s — skipping", vendor)
        return False, f"unknown push vendor {vendor}"

    async def _expo(
        self, to: str, title: str, body: str, data: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        payload: dict = {"to": to, "title": title, "body": body}
        if data:
            payload["data"] = data
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _EXPO_PUSH_URL,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code != 200:
            log.error("Expo push send failed to=%s status=%s", to, resp.status_code)
            return False, f"expo status {resp.status_code}"

        result = resp.json().get("data", {})
        if isinstance(result, dict) and result.get("status") == "error":
            error_detail = (result.get("details") or {}).get("error") or result.get("message") or "expo push error"
            log.error("Expo push error to=%s error=%s", to, error_detail)
            return False, error_detail

        log.info("Expo push sent to=%s title=%s", to, title)
        return True, None
