"""
NotifConsumer — prana.notifications

Dispatches transactional notifications: email via AWS SES, WhatsApp via WABA.

Events handled:
  DOC_ROUTED        → email employee "Your document has been routed to your vault"
  EXCEPTION_RAISED  → email OA-Admin "Exception requires resolution"
  ELEVATION_APPROVED→ email OA-Operator "Your elevation request was approved"
  OA_USER_CREATED   → welcome email with temp password
  TENANT_PROVISIONED→ welcome email for first OA-Admin
"""
import json
import logging
from typing import Optional

import asyncpg
import boto3
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)

GROUP_ID = "prana-notif-consumer"

_SRC = "noreply@prana.in"


class NotifConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._settings = settings
        self._db = db_pool
        self._ses = boto3.client("ses", region_name="ap-south-1")
        self._consumer = AIOKafkaConsumer(
            "prana.notifications",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("NotifConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    if etype == "DOC_ROUTED":
                        await self._notify_doc_routed(event)
                    elif etype == "EXCEPTION_RAISED":
                        await self._notify_exception(event)
                    elif etype == "ELEVATION_APPROVED":
                        await self._notify_elevation(event)
                    elif etype in ("OA_USER_CREATED", "TENANT_PROVISIONED"):
                        await self._notify_welcome(event)
                except Exception:
                    log.exception("NotifConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    def _send(self, to: str, subject: str, body: str) -> None:
        try:
            self._ses.send_email(
                Source=_SRC,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": body}},
                },
            )
            log.info("SES sent to=%s subject=%s", to, subject)
        except Exception:
            log.exception("SES failed to=%s", to)

    async def _lookup_employee_email(self, employee_user_id: str) -> Optional[str]:
        if not self._db:
            return None
        row = await self._db.fetchrow(
            "SELECT email FROM employee_user WHERE employee_user_id = $1", employee_user_id
        )
        return row["email"] if row else None

    async def _lookup_oa_admin_emails(self, tenant_id: str) -> list[str]:
        if not self._db:
            return []
        rows = await self._db.fetch(
            "SELECT email FROM oa_user WHERE tenant_id=$1 AND role='oa_admin' AND status='ACTIVE'",
            tenant_id,
        )
        return [r["email"] for r in rows]

    async def _lookup_oa_user_email(self, oa_user_id: str) -> Optional[str]:
        if not self._db:
            return None
        row = await self._db.fetchrow(
            "SELECT email FROM oa_user WHERE oa_user_id = $1", oa_user_id
        )
        return row["email"] if row else None

    async def _notify_doc_routed(self, event: dict) -> None:
        emp_id = event.get("employee_user_id")
        if not emp_id:
            return
        email = await self._lookup_employee_email(emp_id)
        if not email:
            log.warning("DOC_ROUTED: no email for employee_user_id=%s", emp_id)
            return
        doc_type = event.get("doc_type", "document")
        self._send(
            email,
            "Your document has been added to your PRANA vault",
            f"Hello,\n\nA new {doc_type} has been processed and added to your PRANA career vault.\n\n"
            f"Open the PRANA app to view your document.\n\n— PRANA Platform",
        )

    async def _notify_exception(self, event: dict) -> None:
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            return
        emails = await self._lookup_oa_admin_emails(tenant_id)
        if not emails:
            log.warning("EXCEPTION_RAISED: no OA-Admin found for tenant=%s", tenant_id)
            return
        doc_id    = event.get("document_id", "unknown")
        exception = event.get("exception_type", "PROCESSING_EXCEPTION")
        for email in emails:
            self._send(
                email,
                "Action required: document exception in PRANA",
                f"Hello,\n\nA document processing exception requires your attention.\n\n"
                f"Document ID: {doc_id}\nException: {exception}\n\n"
                f"Log in to the PRANA Portal to resolve this exception.\n\n— PRANA Platform",
            )

    async def _notify_elevation(self, event: dict) -> None:
        oa_user_id = event.get("requestor_id")
        if not oa_user_id:
            return
        email = await self._lookup_oa_user_email(oa_user_id)
        if not email:
            log.warning("ELEVATION_APPROVED: no email for oa_user_id=%s", oa_user_id)
            return
        duration = event.get("duration_hours", "")
        self._send(
            email,
            "Your PRANA elevation request has been approved",
            f"Hello,\n\nYour elevation request has been approved.\n\n"
            f"Duration: {duration} hours\n\n"
            f"Your elevated access is now active. It will expire automatically.\n\n"
            f"— PRANA Platform",
        )

    async def _notify_welcome(self, event: dict) -> None:
        """Send welcome email with temp password to newly created OA user or first OA-Admin."""
        recipient = event.get("admin_email") or event.get("email")
        temp_pw   = event.get("temp_password")
        login_url = event.get("login_url", "https://prana.in/org/login")
        if not recipient or not temp_pw:
            return
        try:
            self._ses.send_email(
                Source="noreply@prana.in",
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": "Welcome to PRANA — your login credentials"},
                    "Body": {"Text": {"Data": (
                        f"Welcome to PRANA.\n\n"
                        f"Your temporary password is: {temp_pw}\n\n"
                        f"Login at: {login_url}\n\n"
                        f"You will be required to set a new password and configure TOTP "
                        f"two-factor authentication on first login.\n\n"
                        f"This password expires after first use.\n\n"
                        f"— PRANA Platform"
                    )}},
                },
            )
            log.info("Welcome email sent to %s", recipient)
        except Exception:
            log.exception("Welcome email failed for %s", recipient)
