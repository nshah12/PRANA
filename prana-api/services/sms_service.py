"""
SMS dispatch via a config-driven vendor chain (AWS SNS, Exotel, MSG91) with
automatic per-vendor failover — vendor order comes entirely from
platform_config/tenant_config's `sms_vendor_chain` (never hardcoded), and a
vendor that's failed repeatedly is skipped via CircuitBreaker until it
recovers. See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4.

Dev mode (settings.sms_provider="dev"): logs OTP to console only, bypasses
the vendor chain entirely. Never sends a real SMS.
All providers use the same interface: send_otp(mobile, code) -> (sent, error).
"""
import logging
from typing import Optional

import boto3
import httpx

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService

log = logging.getLogger(__name__)

CHANNEL = "sms"


class SMSService:
    def __init__(self, settings: Settings, config: ConfigService, breaker: CircuitBreaker) -> None:
        self._settings = settings
        self._config = config
        self._breaker = breaker
        self._provider = getattr(settings, "sms_provider", "dev")

    async def send_otp(
        self, mobile: str, code: str, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if self._provider == "dev":
            log.info("[DEV SMS] mobile=%s code=%s", mobile, code)
            return True, None

        chain = await self._config.get_list(f"{CHANNEL}_vendor_chain", tenant_id)
        if not chain:
            log.error("No %s_vendor_chain configured — cannot send OTP mobile=%s", CHANNEL, mobile)
            return False, "no sms vendor chain configured"

        last_error: Optional[str] = None
        for vendor in chain:
            if await self._breaker.is_open(CHANNEL, vendor):
                log.warning("Circuit open for sms vendor=%s — skipping", vendor)
                continue
            sent, error = await self._dispatch(vendor, mobile, code)
            if sent:
                await self._breaker.record_success(CHANNEL, vendor)
                return True, None
            last_error = error
            await self._breaker.record_failure(CHANNEL, vendor, tenant_id)
        return False, last_error or "all sms vendors in chain exhausted"

    async def _dispatch(self, vendor: str, mobile: str, code: str) -> tuple[bool, Optional[str]]:
        if vendor == "aws":
            return await self._aws_sns(mobile, code)
        elif vendor == "exotel":
            return await self._exotel(mobile, code)
        elif vendor == "msg91":
            return await self._msg91(mobile, code)
        log.warning("Unknown sms vendor %s — skipping", vendor)
        return False, f"unknown sms vendor {vendor}"

    async def _aws_sns(self, mobile: str, code: str) -> tuple[bool, Optional[str]]:
        """AWS SNS direct-to-phone-number publish. Sync boto3 call — same pattern
        already used for SES in email_service.py and for KMS elsewhere in this
        codebase (no async SDK for these AWS services)."""
        s = self._settings
        kwargs: dict = {"region_name": s.aws_region}
        if s.aws_access_key_id:
            kwargs["aws_access_key_id"] = s.aws_access_key_id
            kwargs["aws_secret_access_key"] = s.aws_secret_access_key
        if getattr(s, "sns_endpoint_url", ""):
            kwargs["endpoint_url"] = s.sns_endpoint_url   # LocalStack (dev only)
        client = boto3.client("sns", **kwargs)
        try:
            client.publish(
                PhoneNumber=mobile,
                Message=f"Your PRANA OTP is {code}. Valid for 10 minutes. Do not share.",
                MessageAttributes={
                    "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
                },
            )
            log.info("AWS SNS SMS sent mobile=%s", mobile)
            return True, None
        except Exception as exc:
            log.exception("AWS SNS SMS failed mobile=%s", mobile)
            return False, str(exc)

    async def _exotel(self, mobile: str, code: str) -> tuple[bool, Optional[str]]:
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
            return False, f"exotel status {resp.status_code}"
        log.info("Exotel SMS sent mobile=%s", mobile)
        return True, None

    async def _msg91(self, mobile: str, code: str) -> tuple[bool, Optional[str]]:
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
            return False, f"msg91 status {resp.status_code}"
        log.info("MSG91 SMS sent mobile=%s", mobile)
        return True, None
