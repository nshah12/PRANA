"""
IVR dispatch — Exotel and Ozonetel outbound-call APIs, both configurable via
`ivr_vendor_chain` (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5). Same
config-driven vendor-chain + circuit-breaker shape as every other channel
adapter.

`body` is the flow/campaign ID to play — neither vendor's outbound-call API
accepts freeform text-to-speech content for a triggered notification call.
If empty, each vendor falls back to its own configured default
(exotel_ivr_flow_id / ozonetel_campaign_id).

Dev mode (settings.ivr_provider="dev"): logs to console, bypasses the vendor
chain entirely — same convention as every other channel adapter.

Ozonetel's exact outbound-call param names are flagged unverified against
live vendor docs (see config.py's ozonetel_* settings) — the call shape here
is real and wired, not a stub, but confirm before enabling in production.
"""
import logging
from typing import Optional

import httpx

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService

log = logging.getLogger(__name__)

CHANNEL = "ivr"


class IVRService:
    def __init__(self, settings: Settings, config: ConfigService, breaker: CircuitBreaker) -> None:
        self._settings = settings
        self._config = config
        self._breaker = breaker

    async def send(
        self, *, to: str, body: str, subject: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if getattr(self._settings, "ivr_provider", "dev") == "dev":
            log.info("[DEV IVR] to=%s flow=%s", to, body)
            return True, None

        chain = await self._config.get_list(f"{CHANNEL}_vendor_chain", tenant_id)
        if not chain:
            log.error("No %s_vendor_chain configured — cannot place IVR call to=%s", CHANNEL, to)
            return False, "no ivr vendor chain configured"

        last_error: Optional[str] = None
        for vendor in chain:
            if await self._breaker.is_open(CHANNEL, vendor):
                log.warning("Circuit open for ivr vendor=%s — skipping", vendor)
                continue
            sent, error = await self._dispatch(vendor, to, body)
            if sent:
                await self._breaker.record_success(CHANNEL, vendor)
                return True, None
            last_error = error
            await self._breaker.record_failure(CHANNEL, vendor, tenant_id)
        return False, last_error or "all ivr vendors in chain exhausted"

    async def _dispatch(self, vendor: str, to: str, flow_or_campaign_id: str) -> tuple[bool, Optional[str]]:
        if vendor == "exotel":
            return await self._exotel(to, flow_or_campaign_id)
        elif vendor == "ozonetel":
            return await self._ozonetel(to, flow_or_campaign_id)
        log.warning("Unknown ivr vendor %s — skipping", vendor)
        return False, f"unknown ivr vendor {vendor}"

    async def _exotel(self, to: str, flow_id: str) -> tuple[bool, Optional[str]]:
        s = self._settings
        flow = flow_id or s.exotel_ivr_flow_id
        url = f"https://api.exotel.com/v1/Accounts/{s.exotel_sid}/Calls/connect.json"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                auth=(s.exotel_api_key, s.exotel_api_token),
                data={
                    "From": to,
                    "CallerId": s.exotel_sender_id,
                    "Url": f"http://my.exotel.com/{s.exotel_sid}/exoml/start_voice/{flow}",
                },
            )
        if resp.status_code not in (200, 201):
            log.error("Exotel IVR call failed to=%s status=%s", to, resp.status_code)
            return False, f"exotel status {resp.status_code}"
        log.info("Exotel IVR call initiated to=%s flow=%s", to, flow)
        return True, None

    async def _ozonetel(self, to: str, campaign_id: str) -> tuple[bool, Optional[str]]:
        s = self._settings
        campaign = campaign_id or s.ozonetel_campaign_id
        url = "https://in1-cpaas.ozonetel.com/ozonetel/outbound/call"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                params={
                    "apikey": s.ozonetel_api_key,
                    "username": s.ozonetel_username,
                    "campaign": campaign,
                    "destination": to,
                },
            )
        if resp.status_code not in (200, 201):
            log.error("Ozonetel IVR call failed to=%s status=%s", to, resp.status_code)
            return False, f"ozonetel status {resp.status_code}"
        log.info("Ozonetel IVR call initiated to=%s campaign=%s", to, campaign)
        return True, None
