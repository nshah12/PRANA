"""
SMS dispatch via Exotel (primary) or MSG91 (fallback).

Provider selection:
  settings.sms_provider = "exotel" | "msg91" | "dev"

Dev mode: logs OTP to console only. Never sends a real SMS.
All providers use the same interface: send_otp(mobile, code).
"""
import logging

import httpx

from config import Settings

log = logging.getLogger(__name__)


class SMSService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = getattr(settings, "sms_provider", "dev")

    async def send_otp(self, mobile: str, code: str) -> None:
        if self._provider == "dev":
            log.info("[DEV SMS] mobile=%s code=%s", mobile, code)
            return
        if self._provider == "exotel":
            await self._exotel(mobile, code)
        elif self._provider == "msg91":
            await self._msg91(mobile, code)
        else:
            log.warning("Unknown SMS provider %s — dropping OTP for %s", self._provider, mobile)

    async def _exotel(self, mobile: str, code: str) -> None:
        s = self._settings
        url = (
            f"https://api.exotel.com/v1/Accounts/{s.exotel_sid}"
            f"/Sms/send.json"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                auth=(s.exotel_api_key, s.exotel_api_token),
                data={
                    "From": s.exotel_sender_id,
                    "To": mobile,
                    "Body": f"Your PRANA OTP is {code}. Valid for 10 minutes. Do not share.",
                },
            )
        if resp.status_code not in (200, 201):
            log.error("Exotel SMS failed mobile=%s status=%s", mobile, resp.status_code)
        else:
            log.info("Exotel SMS sent mobile=%s", mobile)

    async def _msg91(self, mobile: str, code: str) -> None:
        s = self._settings
        # MSG91 OTP API v5
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/otp",
                headers={"authkey": s.msg91_auth_key, "Content-Type": "application/json"},
                json={
                    "template_id": s.msg91_template_id,
                    "mobile": mobile.lstrip("+"),
                    "otp": code,
                },
            )
        if resp.status_code != 200:
            log.error("MSG91 SMS failed mobile=%s status=%s", mobile, resp.status_code)
        else:
            log.info("MSG91 SMS sent mobile=%s", mobile)
