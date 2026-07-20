"""
SMS dispatch via AWS SNS, Exotel, or MSG91 — selected per environment.

Provider selection:
  settings.sms_provider = "aws" | "exotel" | "msg91" | "dev"

Dev mode: logs OTP to console only. Never sends a real SMS.
All providers use the same interface: send_otp(mobile, code).
"""
import logging

import boto3
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
        if self._provider == "aws":
            await self._aws_sns(mobile, code)
        elif self._provider == "exotel":
            await self._exotel(mobile, code)
        elif self._provider == "msg91":
            await self._msg91(mobile, code)
        else:
            log.warning("Unknown SMS provider %s — dropping OTP for %s", self._provider, mobile)

    async def _aws_sns(self, mobile: str, code: str) -> None:
        """AWS SNS direct-to-phone-number publish. Sync boto3 call — same pattern
        already used for SES in notification_service.py and for KMS elsewhere in
        this codebase (no async SDK for these AWS services)."""
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
        except Exception:
            log.exception("AWS SNS SMS failed mobile=%s", mobile)

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
