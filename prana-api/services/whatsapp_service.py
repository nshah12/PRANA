"""
WhatsApp dispatch via Meta Cloud API (WABA) — Communication Hub channel
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4-5). Single-vendor chain for
v1 (§10 — WABA is the only real option for most Indian deployments), but
still goes through the same config-driven vendor-chain + circuit-breaker
shape as every other channel adapter, so a second vendor (e.g. a BSP like
Gupshup/Twilio) can be added later by extending whatsapp_vendor_chain and
_dispatch — no caller changes required.

Meta restricts WhatsApp Business messages to pre-approved templates — never
freeform text (.claude/rules/integrations.md). `body` is therefore the
approved template *name*, not message content; `template_params` fills the
template's numbered placeholders ({{1}}, {{2}}, ...) when it has any.

Dev mode (settings.whatsapp_provider="dev"): logs to console, bypasses the
vendor chain entirely — same convention as every other channel adapter.
"""
import logging
from typing import Optional

import httpx

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService

log = logging.getLogger(__name__)

CHANNEL = "whatsapp"


class WhatsAppService:
    def __init__(self, settings: Settings, config: ConfigService, breaker: CircuitBreaker) -> None:
        self._settings = settings
        self._config = config
        self._breaker = breaker

    async def send(
        self, *, to: str, body: str, subject: Optional[str] = None,
        template_params: Optional[list[str]] = None, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if getattr(self._settings, "whatsapp_provider", "dev") == "dev":
            log.info("[DEV WHATSAPP] to=%s template=%s", to, body)
            return True, None

        chain = await self._config.get_list(f"{CHANNEL}_vendor_chain", tenant_id)
        if not chain:
            log.error("No %s_vendor_chain configured — cannot send WhatsApp to=%s", CHANNEL, to)
            return False, "no whatsapp vendor chain configured"

        last_error: Optional[str] = None
        for vendor in chain:
            if await self._breaker.is_open(CHANNEL, vendor):
                log.warning("Circuit open for whatsapp vendor=%s — skipping", vendor)
                continue
            sent, error = await self._dispatch(vendor, to, body, template_params)
            if sent:
                await self._breaker.record_success(CHANNEL, vendor)
                return True, None
            last_error = error
            await self._breaker.record_failure(CHANNEL, vendor, tenant_id)
        return False, last_error or "all whatsapp vendors in chain exhausted"

    async def _dispatch(
        self, vendor: str, to: str, template_name: str, template_params: Optional[list[str]],
    ) -> tuple[bool, Optional[str]]:
        if vendor == "waba":
            return await self._waba(to, template_name, template_params)
        log.warning("Unknown whatsapp vendor %s — skipping", vendor)
        return False, f"unknown whatsapp vendor {vendor}"

    async def _waba(
        self, to: str, template_name: str, template_params: Optional[list[str]],
    ) -> tuple[bool, Optional[str]]:
        s = self._settings
        url = f"https://graph.facebook.com/{s.whatsapp_waba_api_version}/{s.whatsapp_waba_phone_number_id}/messages"
        template: dict = {"name": template_name, "language": {"code": "en"}}
        if template_params:
            template["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in template_params],
            }]
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "template",
            "template": template,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {s.whatsapp_waba_token}"},
                json=payload,
            )
        if resp.status_code not in (200, 201):
            log.error("WABA WhatsApp send failed to=%s status=%s", to, resp.status_code)
            return False, f"waba status {resp.status_code}"
        log.info("WABA WhatsApp sent to=%s template=%s", to, template_name)
        return True, None
