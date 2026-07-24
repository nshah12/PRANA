"""
IVR dispatch — Exotel and Ozonetel outbound-call APIs, both configurable via
`ivr_vendor_chain` (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5). Same
config-driven vendor-chain + circuit-breaker shape as every other channel
adapter.

`body`'s meaning is vendor-dependent — the two vendors genuinely don't offer
the same capability here:
  - Exotel: `body` is a flow/Applet ID — Exotel's outbound-call API connects
    the call to a pre-built ExoML flow, no freeform text accepted. Falls
    back to exotel_ivr_flow_id if empty.
  - Ozonetel (KooKoo): `body` is played as literal text-to-speech via the
    documented `extra_data` playtext mechanism — this vendor's API genuinely
    does accept freeform text for a triggered call, unlike Exotel.

Dev mode (settings.ivr_provider="dev"): logs to console, bypasses the vendor
chain entirely — same convention as every other channel adapter.

Ozonetel's shape (endpoint, GET method, param names, XML response format) is
verified against real docs.ozonetel.com / KooKoo documentation (2026-07-24) —
see _ozonetel()'s docstring for the source. Note KooKoo's own documented
constraints: standard accounts are capped at 50 outbound calls/day, and TRAI
regulations block calls between 9pm-9am IST — neither is enforced here, both
are the vendor's own limits to plan around operationally.
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

    async def _ozonetel(self, to: str, message: str) -> tuple[bool, Optional[str]]:
        """Ozonetel/KooKoo outbound call — GET http://in1-cpaas.ozonetel.com/outbound/outbound.php,
        api_key + phone_no required, outbound_version=2, extra_data carries a
        <response><playtext>...</playtext><hangup/></response> XML block that's
        read aloud via TTS. Success is reported in the XML body
        (<status>queued</status>), not just the HTTP status — a 200 response can
        still carry <status>error</status> (e.g. bad api_key). Documented at
        docs.ozonetel.com's Outbound Call API / KooKoo docs, verified 2026-07-24."""
        s = self._settings
        text = message or "You have a notification from PRANA."
        extra_data = f"<response><playtext>{text}</playtext><hangup/></response>"
        params: dict = {
            "api_key": s.ozonetel_api_key,
            "phone_no": to.lstrip("+"),
            "outbound_version": "2",
            "extra_data": extra_data,
        }
        if s.ozonetel_caller_id:
            params["caller_id"] = s.ozonetel_caller_id
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "http://in1-cpaas.ozonetel.com/outbound/outbound.php",
                params=params,
            )
        if resp.status_code != 200 or "<status>queued</status>" not in resp.text:
            log.error("Ozonetel IVR call failed to=%s status=%s body=%s", to, resp.status_code, resp.text[:200])
            return False, f"ozonetel status {resp.status_code}"
        log.info("Ozonetel IVR call queued to=%s", to)
        return True, None
