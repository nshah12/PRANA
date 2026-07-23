"""
Email dispatch via a config-driven vendor chain (SES, SMTP, ...) with
automatic per-vendor failover — vendor order comes entirely from
platform_config/tenant_config's `email_vendor_chain` (never hardcoded), and
a vendor that's failed repeatedly is skipped via CircuitBreaker until it
recovers. See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4.

Dev mode (settings.email_provider="dev"): logs to console, bypasses the
vendor chain entirely — no Redis/DB dependency needed for local dev, same
convention already used by SMSService/KMSService endpoint overrides.

All providers use the same interface: send_email(to, subject, body) -> (sent, error).
Callers (NotificationService, CommunicationHubConsumer) depend only on this
interface, never on boto3 or smtplib directly.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import boto3

from config import Settings
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService

log = logging.getLogger(__name__)

CHANNEL = "email"


class EmailService:
    def __init__(self, settings: Settings, config: ConfigService, breaker: CircuitBreaker) -> None:
        self._settings = settings
        self._config = config
        self._breaker = breaker
        self._provider = getattr(settings, "email_provider", "dev")

    async def send_email(
        self, *, to: str, subject: str, body: str, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if self._provider == "dev":
            log.info("[DEV EMAIL] to=%s subject=%s", to, subject)
            return True, None

        chain = await self._config.get_list(f"{CHANNEL}_vendor_chain", tenant_id)
        if not chain:
            log.error("No %s_vendor_chain configured — cannot send email to=%s", CHANNEL, to)
            return False, "no email vendor chain configured"

        last_error: Optional[str] = None
        for vendor in chain:
            if await self._breaker.is_open(CHANNEL, vendor):
                log.warning("Circuit open for email vendor=%s — skipping", vendor)
                continue
            sent, error = self._dispatch(vendor, to, subject, body)
            if sent:
                await self._breaker.record_success(CHANNEL, vendor)
                return True, None
            last_error = error
            await self._breaker.record_failure(CHANNEL, vendor, tenant_id)
        return False, last_error or "all email vendors in chain exhausted"

    def _dispatch(self, vendor: str, to: str, subject: str, body: str) -> tuple[bool, Optional[str]]:
        if vendor == "ses":
            return self._ses(to, subject, body)
        elif vendor == "smtp":
            return self._smtp(to, subject, body)
        log.warning("Unknown email vendor %s — skipping", vendor)
        return False, f"unknown email vendor {vendor}"

    def _ses(self, to: str, subject: str, body: str) -> tuple[bool, Optional[str]]:
        """AWS SES SendEmail. Sync boto3 call — same pattern already used for
        SNS in sms_service.py and for KMS elsewhere in this codebase (no async
        SDK for these AWS services)."""
        s = self._settings
        kwargs: dict = {"region_name": s.aws_region}
        if s.aws_access_key_id:
            kwargs["aws_access_key_id"] = s.aws_access_key_id
            kwargs["aws_secret_access_key"] = s.aws_secret_access_key
        if getattr(s, "ses_endpoint_url", ""):
            kwargs["endpoint_url"] = s.ses_endpoint_url   # LocalStack (dev only)
        client = boto3.client("ses", **kwargs)
        try:
            client.send_email(
                Source=s.smtp_from,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": body}},
                },
            )
            log.info("SES email sent to=%s subject=%s", to, subject)
            return True, None
        except Exception as exc:
            log.exception("SES email failed to=%s", to)
            return False, str(exc)

    def _smtp(self, to: str, subject: str, body: str) -> tuple[bool, Optional[str]]:
        """Generic SMTP — SendGrid, Postmark, Mailgun, or any other
        SMTP-speaking provider. Selected via a "smtp" entry in the vendor chain."""
        s = self._settings
        msg = MIMEMultipart()
        msg["From"] = s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
                if s.smtp_use_tls:
                    server.starttls()
                if s.smtp_user:
                    server.login(s.smtp_user, s.smtp_password)
                server.sendmail(s.smtp_from, [to], msg.as_string())
            log.info("SMTP email sent to=%s subject=%s", to, subject)
            return True, None
        except Exception as exc:
            log.exception("SMTP email failed to=%s", to)
            return False, str(exc)
