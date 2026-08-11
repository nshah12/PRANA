"""
Shared constants, enums, and helpers for the Communication Hub's per-channel
consumers (EmailConsumer, SMSConsumer, WhatsAppConsumer, PushConsumer):
Channel/RecipientType enums, the NotificationTemplate -> subject line map
(_SUBJECT_MAP, enforced by tests/test_messages.py), _build_email_body, and the
_check_template_data privacy guard (template_data must never contain PAN or
raw salary keys — every per-channel consumer calls this before dispatch or
writing to notification_log).

The NotificationService class that used to live here (notify()/notify_anomaly(),
an inline dispatch path with stubbed SMS/WhatsApp/push) was removed 2026-08-10 —
dead code, its one real caller was NotificationDeliveryWorkflow (removed the
same day, see workflows/CLAUDE.md). Each channel now dispatches for real via its
own {Channel}Service (config-driven vendor chain + circuit breaker) directly,
and writes notification_log via services/notification_log.py — see
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4. Removing it also
surfaced that _check_template_data had never actually been wired into any of
those real consumers (only the dead class called it) — fixed alongside this
removal; every per-channel consumer now calls it before dispatch.
"""
from enum import Enum
from typing import Any

from messages import NotificationTemplate

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
