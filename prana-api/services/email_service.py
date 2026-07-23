"""
Email dispatch via AWS SES or generic SMTP — selected per environment.

Provider selection:
  settings.email_provider = "ses" | "smtp" | "dev"

Dev mode: logs the email to console only. Never sends a real email.
All providers use the same interface: send_email(to, subject, body) -> (sent, error).

Switching providers (e.g. to SendGrid, or any other SMTP-speaking service)
needs no code change — set email_provider="smtp" and the smtp_* settings.
Callers (NotificationService) depend only on this interface, never on boto3
or smtplib directly.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import boto3

from config import Settings

log = logging.getLogger(__name__)


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = getattr(settings, "email_provider", "dev")

    def send_email(self, *, to: str, subject: str, body: str) -> tuple[bool, Optional[str]]:
        if self._provider == "dev":
            log.info("[DEV EMAIL] to=%s subject=%s", to, subject)
            return True, None
        if self._provider == "ses":
            return self._ses(to, subject, body)
        elif self._provider == "smtp":
            return self._smtp(to, subject, body)
        else:
            log.warning("Unknown email provider %s — dropping email to=%s", self._provider, to)
            return False, f"unknown email provider {self._provider}"

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
        SMTP-speaking provider. Selected via email_provider="smtp"."""
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
