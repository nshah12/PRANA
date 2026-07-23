"""
NotificationService — writes notification_log and dispatches via channel.

As of the Communication Hub redesign (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md),
CommunicationHubConsumer and the per-channel consumers (EmailConsumer,
SMSConsumer, WhatsAppConsumer, IVRConsumer) no longer call notify() —
they publish/consume via Kafka and dispatch through {Channel}Service directly,
using services/notification_log.py for the notification_log write.
notify()/notify_anomaly() remain here for their one real remaining caller,
services/platform_ops_service.py's NotificationDeliveryWorkflow activities
(a Temporal-driven delivery path, separate from the Kafka Hub) — never call
this from HTTP handlers.
Privacy guards: template_data must not contain PAN or raw salary keys.
"""
import json
import logging
from enum import Enum
from typing import Any, Optional

import asyncpg
import redis.asyncio as redis

from config import Settings, get_settings
from messages import NotificationTemplate
from services.circuit_breaker import CircuitBreaker
from services.config_service import ConfigService
from services.email_service import EmailService

log = logging.getLogger(__name__)

_BANNED_TEMPLATE_KEYS = {
    "pan", "enc_pan", "nik", "pan_token",
    "gross_salary", "net_salary", "basic_salary", "ctc", "salary",
}

# One entry per NotificationTemplate member — enforced by
# tests/test_messages.py::test_every_notification_template_has_a_subject_line.
_SUBJECT_MAP: dict[str, str] = {
    NotificationTemplate.ANOMALY_P0_ALERT:  "[CRITICAL] PRANA Security Anomaly — Immediate action required",
    NotificationTemplate.ANOMALY_P1_ALERT:  "[HIGH] PRANA Security Anomaly detected",
    NotificationTemplate.ANOMALY_P2_ALERT:  "[MEDIUM] PRANA Security Anomaly logged",
    NotificationTemplate.ACCOUNT_LOCKED:    "PRANA: Account locked",
    NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT: "[CRITICAL] PRANA: Cross-tenant upload attempt detected",
    NotificationTemplate.AUDIT_INTEGRITY_MISMATCH:  "[CRITICAL] PRANA: Audit integrity mismatch detected",
    NotificationTemplate.DOC_ROUTED:        "Your document has been added to your PRANA vault",
    NotificationTemplate.SHARE_ACCESSED:    "Your PRANA document share was accessed",
    NotificationTemplate.ERASURE_COMPLETE:  "PRANA: Your data erasure is complete",
    NotificationTemplate.EXPORT_READY:      "PRANA: Your data export is ready",
    NotificationTemplate.EXCEPTION_ALERT:   "Action required: PRANA document exception",
    NotificationTemplate.ELEVATION_APPROVED: "PRANA: Your elevation request was approved",
    NotificationTemplate.ELEVATION_DENIED:  "PRANA: Your elevation request was denied",
    NotificationTemplate.OA_WELCOME:        "Welcome to PRANA — your login credentials",
    NotificationTemplate.INCIDENT_CREATED:  "PRANA Incident created — review required",
    NotificationTemplate.INCIDENT_SLA_BREACH: "PRANA Incident SLA breached",
    NotificationTemplate.CSAM_ALERT:        "[URGENT] PRANA content alert — immediate action",
    NotificationTemplate.DIGEST_WEEKLY:     "Your PRANA weekly digest is ready",
    NotificationTemplate.VAULT_WELCOME:         "Your PRANA vault is ready",
    NotificationTemplate.VAULT_WELCOME_REJOIN:  "Welcome back to PRANA",
    NotificationTemplate.EMPLOYEE_CREDENTIALS_ISSUED: "Your PRANA account is ready — set up your login",
    NotificationTemplate.STORAGE_EXPANSION_REQUESTED: "PRANA: Tenant storage expansion request awaiting review",
    NotificationTemplate.ONBOARDING_REVIEW_SLA_BREACH: "PRANA: Onboarding review SLA breached — action required",
    NotificationTemplate.ELEVATION_EXPIRED:      "PRANA: Your elevation access has expired",
    NotificationTemplate.DIGEST_MONTHLY:         "Your PRANA monthly digest is ready",
    NotificationTemplate.OBLIGATION_DUE:         "PRANA: Statutory obligation due soon",
    NotificationTemplate.ALUMNI_OUTREACH_RECEIVED: "You've received a message via PRANA Alumni Network",
}


class Channel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    PUSH = "PUSH"
    PORTAL_BELL = "PORTAL_BELL"


class RecipientType(str, Enum):
    OA_USER = "OA_USER"
    EMPLOYEE = "EMPLOYEE"
    PORTAL_ADMIN = "PORTAL_ADMIN"


def _check_template_data(template_data: dict[str, Any]) -> None:
    """Raise ValueError if template_data contains PAN or salary keys."""
    lower_keys = {k.lower() for k in template_data}
    pan_hit = lower_keys & {"pan", "enc_pan", "nik"}
    if pan_hit:
        raise ValueError(f"template_data contains PAN/NIK key: {pan_hit}")
    salary_hit = lower_keys & {"gross_salary", "net_salary", "basic_salary", "ctc", "salary"}
    if salary_hit:
        raise ValueError(f"template_data contains raw salary key: {salary_hit}")


def _build_email_body(template_id: str, template_data: dict[str, Any]) -> str:
    """Render a simple text body from template_id + template_data."""
    parts = [f"PRANA Platform Notification\n{'—'*40}\n"]
    for k, v in template_data.items():
        parts.append(f"{k}: {v}")
    parts.append("\n— PRANA Platform\nnoreply@prana.in")
    return "\n".join(parts)


class NotificationService:
    def __init__(
        self,
        db: asyncpg.Connection,
        settings: Optional[Settings] = None,
        redis_client: Optional[redis.Redis] = None,
    ) -> None:
        self._db = db
        config = ConfigService(db, redis_client)
        breaker = CircuitBreaker(redis_client, config)
        self._email = EmailService(settings or get_settings(), config, breaker)

    async def notify(
        self,
        *,
        tenant_id: Optional[str],
        event_type: str,
        recipient_id: str,
        recipient_type: RecipientType,
        channel: Channel,
        template_id: str,
        template_data: dict[str, Any],
        recipient_email: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        source_id: Optional[str] = None,
        source_table: Optional[str] = None,
        check_suppression: bool = False,
    ) -> None:
        """Dispatch a single notification and record it in notification_log."""
        _check_template_data(template_data)

        status = "QUEUED"
        error_message: Optional[str] = None

        # Suppression check for email bounces
        if channel == Channel.EMAIL and check_suppression and recipient_email:
            suppressed = await self._is_suppressed(recipient_email)
            if suppressed:
                status = "SUPPRESSED"
                await self._log(
                    tenant_id=tenant_id,
                    event_type=event_type,
                    recipient_id=recipient_id,
                    recipient_type=recipient_type,
                    recipient_email=recipient_email,
                    recipient_phone=recipient_phone,
                    channel=channel,
                    template_id=template_id,
                    template_data=template_data,
                    source_id=source_id,
                    source_table=source_table,
                    status=status,
                )
                return

        if channel == Channel.EMAIL:
            if not recipient_email:
                log.warning("EMAIL channel requested but no recipient_email event_type=%s", event_type)
                return
            sent, error_message = await self._send_email(
                to=recipient_email,
                subject=_SUBJECT_MAP.get(template_id, "PRANA Notification"),
                body=_build_email_body(template_id, template_data),
                tenant_id=tenant_id,
            )
            status = "SENT" if sent else "FAILED"

        elif channel == Channel.PORTAL_BELL:
            # Portal bell is a DB-only record — no external dispatch
            status = "SENT"

        elif channel in (Channel.SMS, Channel.WHATSAPP, Channel.PUSH):
            # Stub — in production these call SMS/WhatsApp/push APIs
            log.info("Channel %s dispatch stub event_type=%s recipient=%s",
                     channel.value, event_type, recipient_id)
            status = "SENT"

        await self._log(
            tenant_id=tenant_id,
            event_type=event_type,
            recipient_id=recipient_id,
            recipient_type=recipient_type,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone,
            channel=channel,
            template_id=template_id,
            template_data=template_data,
            source_id=source_id,
            source_table=source_table,
            status=status,
            error_message=error_message,
        )

    async def notify_anomaly(
        self,
        *,
        tenant_id: str,
        anomaly_id: str,
        rule_name: str,
        severity: str,
        ciso_id: str,
        ciso_email: str,
    ) -> None:
        """Dispatch notifications appropriate for the anomaly severity."""
        if severity == "P3":
            # P3: no notification — dashboard shows it via anomaly_event query
            return

        template_data = {
            "rule_name": rule_name,
            "severity": severity,
            "anomaly_id": anomaly_id,
        }

        if severity in ("P0", "P1"):
            template_id = (NotificationTemplate.ANOMALY_P0_ALERT if severity == "P0"
                            else NotificationTemplate.ANOMALY_P1_ALERT)
            await self.notify(
                tenant_id=tenant_id,
                event_type="ANOMALY_DETECTED",
                recipient_id=ciso_id,
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso_email,
                channel=Channel.EMAIL,
                template_id=template_id,
                template_data=template_data,
                source_id=anomaly_id,
                source_table="anomaly_event",
            )

        # Portal bell for P0, P1, P2
        await self.notify(
            tenant_id=tenant_id,
            event_type="ANOMALY_DETECTED",
            recipient_id=ciso_id,
            recipient_type=RecipientType.OA_USER,
            channel=Channel.PORTAL_BELL,
            template_id=NotificationTemplate.ANOMALY_P2_ALERT if severity == "P2" else (
                NotificationTemplate.ANOMALY_P0_ALERT if severity == "P0" else NotificationTemplate.ANOMALY_P1_ALERT
            ),
            template_data=template_data,
            source_id=anomaly_id,
            source_table="anomaly_event",
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _send_email(
        self, *, to: str, subject: str, body: str, tenant_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        # Delegates to EmailService — vendor chain (SES, SMTP/SendGrid, ...)
        # is config-driven (email_vendor_chain), never hardcoded here.
        return await self._email.send_email(to=to, subject=subject, body=body, tenant_id=tenant_id)

    async def _is_suppressed(self, email: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT email FROM email_suppression WHERE email = $1", email
        )
        return row is not None

    async def _log(
        self,
        *,
        tenant_id: Optional[str],
        event_type: str,
        recipient_id: str,
        recipient_type: RecipientType,
        channel: Channel,
        template_id: str,
        template_data: dict[str, Any],
        status: str,
        recipient_email: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        source_id: Optional[str] = None,
        source_table: Optional[str] = None,
        provider_ref: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        from datetime import datetime, timezone
        sent_at = datetime.now(timezone.utc) if status == "SENT" else None
        failed_at = datetime.now(timezone.utc) if status == "FAILED" else None

        await self._db.execute(
            """
            INSERT INTO notification_log
              (tenant_id, event_type, source_id, source_table,
               recipient_id, recipient_type, recipient_email, recipient_phone,
               channel, template_id, template_data,
               status, provider_ref, sent_at, failed_at, error_message)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            """,
            tenant_id, event_type, source_id, source_table,
            recipient_id, recipient_type.value, recipient_email, recipient_phone,
            channel.value, template_id, json.dumps(template_data),
            status, provider_ref, sent_at, failed_at, error_message,
        )
