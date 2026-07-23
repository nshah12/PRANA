"""
CommunicationHubConsumer — prana.communications.events (+ legacy prana.notifications)

Renamed/repurposed from NotifConsumer. The Hub decides WHICH channel(s) a
notification goes out on — nothing else does. Every handler resolves a
recipient (same DB lookups as before) and a NotificationTemplate, then calls
_fan_out(), which is the only place that:
  1. looks up notification_channel_policy (tenant override -> platform default)
  2. publishes to each decided channel's own topic (prana.notifications.{channel})
Per-channel consumers (EmailConsumer, SMSConsumer, WhatsAppConsumer,
BellConsumer, IVRConsumer, PushConsumer) pick those up and call the real
vendor adapter. The Hub itself never touches EmailService/SMSService/etc.,
and no longer calls NotificationService.notify() at all — see
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §2, §7.

Two intake topics during the migration window (§2.1 — the old topic is
retired once every existing producer moves to communication_requested()):
  prana.communications.events — NEW generic entrypoint: {template_id,
      recipient_id, recipient_type, tenant_id, template_data, recipient_email?,
      recipient_phone?, event_type?}. No recipient DB lookup needed — the
      caller already resolved it.
  prana.notifications — legacy rich domain events (ANOMALY_DETECTED,
      DOC_ROUTED, EXCEPTION_RAISED, ...). Handlers below do the recipient
      lookup, same as before, then call _fan_out().

Events handled (unchanged from CommunicationHubConsumer — see git history for the full
per-event-type rationale):
  ANOMALY_DETECTED, DOC_ROUTED, EXCEPTION_RAISED, ELEVATION_APPROVED/DENIED,
  TENANT_PROVISIONED, ACCOUNT_LOCKED, CROSS_TENANT_UPLOAD, DPDP_ERASURE_DONE,
  DPDP_EXPORT_READY, SHARE_ACCESSED, AUDIT_INTEGRITY_MISMATCH,
  VAULT_WELCOME(_REJOIN)/EMPLOYEE_CREDENTIALS_ISSUED, STORAGE_EXPANSION_REQUESTED,
  ONBOARDING_REVIEW_SLA_BREACH — plus COMMUNICATION_REQUESTED on the new topic.
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import TOPIC_COMM, TOPIC_NOTIF, get_kafka_producer
from messages import NotificationTemplate
from services.channel_policy_service import ChannelPolicyService
from services.encryption_service import resolve_platform_auth_kek_arn
from services.incident_service import IncidentService
from services.notification_service import Channel, RecipientType

log = logging.getLogger(__name__)

GROUP_ID = "prana-communication-hub-consumer"

_ANOMALY_TEMPLATE_BY_SEVERITY = {
    "P0": NotificationTemplate.ANOMALY_P0_ALERT,
    "P1": NotificationTemplate.ANOMALY_P1_ALERT,
    "P2": NotificationTemplate.ANOMALY_P2_ALERT,
}

_CHANNEL_DISPATCH = {
    "email":       "notify_email",
    "sms":         "notify_sms",
    "whatsapp":    "notify_whatsapp",
    "portal_bell": "notify_bell",
    "ivr":         "notify_ivr",
    "push":        "notify_push",
}


class CommunicationHubConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, kms_service=None,
    ) -> None:
        self._settings = settings
        self._db_pool = db_pool
        self._kms = kms_service
        self._consumer = AIOKafkaConsumer(
            TOPIC_COMM, TOPIC_NOTIF,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("CommunicationHubConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    async with self._db_pool.acquire() as conn:
                        isvc = IncidentService(db=conn)
                        await self._dispatch(event, etype, msg.topic, isvc, conn)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._db_pool, consumer_name="CommunicationHubConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("CommunicationHubConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(
        self, event: dict, etype: Optional[str], topic: str, isvc: IncidentService, conn: asyncpg.Connection,
    ) -> None:
        if topic == TOPIC_COMM:
            await self._handle_communication_requested(event, conn)
            return

        if etype == "ANOMALY_DETECTED":
            await self._handle_anomaly(event, isvc, conn)
        elif etype == "DOC_ROUTED":
            await self._handle_doc_routed(event, conn)
        elif etype == "EXCEPTION_RAISED":
            await self._handle_exception(event, conn)
        elif etype == "ELEVATION_APPROVED":
            await self._handle_elevation(event, conn, approved=True)
        elif etype == "ELEVATION_DENIED":
            await self._handle_elevation(event, conn, approved=False)
        elif etype == "TENANT_PROVISIONED":
            await self._handle_welcome(event, etype, conn)
        elif etype == "ACCOUNT_LOCKED":
            await self._handle_account_locked(event, conn)
        elif etype == "CROSS_TENANT_UPLOAD":
            await self._handle_cross_tenant_upload(event, conn)
        elif etype == "DPDP_ERASURE_DONE":
            await self._handle_dpdp_employee(event, conn, template_id=NotificationTemplate.ERASURE_COMPLETE)
        elif etype == "DPDP_EXPORT_READY":
            await self._handle_dpdp_employee(event, conn, template_id=NotificationTemplate.EXPORT_READY)
        elif etype == "SHARE_ACCESSED":
            await self._handle_dpdp_employee(event, conn, template_id=NotificationTemplate.SHARE_ACCESSED)
        elif etype == "AUDIT_INTEGRITY_MISMATCH":
            await self._handle_audit_integrity_mismatch(event, conn)
        elif etype in ("VAULT_WELCOME", "VAULT_WELCOME_REJOIN", "EMPLOYEE_CREDENTIALS_ISSUED"):
            await self._handle_employee_welcome(event, etype, conn)
        elif etype == "STORAGE_EXPANSION_REQUESTED":
            await self._handle_storage_expansion_requested(event, conn)
        elif etype == "ONBOARDING_REVIEW_SLA_BREACH":
            await self._handle_onboarding_review_sla_breach(event, conn)
        else:
            log.debug("CommunicationHubConsumer: unhandled event_type=%s", etype)

    # -----------------------------------------------------------------------
    # The one place a channel decision is made
    # -----------------------------------------------------------------------

    async def _fan_out(
        self,
        *,
        template_id: str,
        tenant_id: Optional[str],
        recipient_id: str,
        recipient_type: RecipientType,
        template_data: dict,
        event_type: str,
        conn: asyncpg.Connection,
        recipient_email: Optional[str] = None,
        recipient_phone: Optional[str] = None,
    ) -> None:
        channels = await ChannelPolicyService(conn).resolve(template_id, tenant_id)
        if not channels:
            log.debug("CommunicationHubConsumer: no channel policy for template_id=%s — nothing dispatched", template_id)
            return

        kafka = await get_kafka_producer()
        payload = {
            "event_type": event_type,
            "template_id": template_id,
            "template_data": template_data,
            "recipient_id": recipient_id,
            "recipient_type": recipient_type,
            "tenant_id": tenant_id,
            "recipient_email": recipient_email,
            "recipient_phone": recipient_phone,
        }
        for channel in channels:
            method_name = _CHANNEL_DISPATCH.get(channel)
            if not method_name:
                log.warning("CommunicationHubConsumer: unknown channel=%s in policy for template_id=%s", channel, template_id)
                continue
            await getattr(kafka, method_name)(payload)

    async def _handle_communication_requested(self, event: dict, conn: asyncpg.Connection) -> None:
        template_id = event.get("template_id")
        recipient_id = event.get("recipient_id")
        if not template_id or not recipient_id:
            log.warning("CommunicationHubConsumer: communication_requested missing template_id/recipient_id")
            return
        await self._fan_out(
            template_id=template_id,
            tenant_id=event.get("tenant_id"),
            recipient_id=str(recipient_id),
            recipient_type=event.get("recipient_type", RecipientType.EMPLOYEE),
            template_data=event.get("template_data") or {},
            event_type=event.get("event_type", template_id),
            conn=conn,
            recipient_email=event.get("recipient_email"),
            recipient_phone=event.get("recipient_phone"),
        )

    # -----------------------------------------------------------------------
    # Handlers — recipient resolution unchanged from CommunicationHubConsumer, channel
    # decision replaced with _fan_out()
    # -----------------------------------------------------------------------

    async def _handle_anomaly(self, event: dict, isvc: IncidentService, conn: asyncpg.Connection) -> None:
        tenant_id   = event.get("tenant_id")
        anomaly_id  = event.get("anomaly_id")
        rule_name   = event.get("rule_name", "UNKNOWN")
        severity    = event.get("severity")
        if not severity:
            from services.severity_policy_service import SeverityPolicyService
            severity = await SeverityPolicyService(conn).resolve_severity(
                domain="ANOMALY_RULE", value=rule_name,
            ) or "P3"

        ciso = await self._lookup_ciso(conn, tenant_id)
        template_id = _ANOMALY_TEMPLATE_BY_SEVERITY.get(severity)
        if ciso and template_id:
            await self._fan_out(
                template_id=template_id,
                tenant_id=tenant_id,
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso["email"],
                template_data={"rule_name": rule_name, "severity": severity, "anomaly_id": anomaly_id},
                event_type="ANOMALY_DETECTED",
                conn=conn,
            )

        await isvc.auto_create_for_anomaly(
            anomaly_id=anomaly_id,
            tenant_id=tenant_id,
            rule_name=rule_name,
            severity=severity,
            assigned_ciso_id=str(ciso["oa_user_id"]) if ciso else None,
        )

    def _decrypt_mobile(self, enc_mobile: Optional[str]) -> Optional[str]:
        """Decrypts enc_mobile via the platform auth CMK — same model as
        totp_secret_enc (see .claude/rules/security.md's Encryption stack section)."""
        if not enc_mobile or not self._kms:
            return None
        kek_arn = resolve_platform_auth_kek_arn(self._settings)
        return self._kms.decrypt_value(enc_mobile, kek_arn)

    async def _handle_doc_routed(self, event: dict, conn: asyncpg.Connection) -> None:
        emp_id   = event.get("employee_user_id")
        doc_type = event.get("doc_type", "document")
        tenant_id = event.get("tenant_id")
        if not emp_id:
            return

        row = await conn.fetchrow(
            "SELECT email, enc_mobile FROM employee_user WHERE employee_user_id = $1", emp_id
        )
        if not row:
            log.warning("DOC_ROUTED: employee not found employee_user_id=%s", emp_id)
            return

        await self._fan_out(
            template_id=NotificationTemplate.DOC_ROUTED,
            tenant_id=tenant_id,
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_phone=self._decrypt_mobile(row["enc_mobile"]),
            template_data={"doc_type": doc_type},
            event_type="DOC_ROUTED",
            conn=conn,
        )

    async def _handle_exception(self, event: dict, conn: asyncpg.Connection) -> None:
        tenant_id    = event.get("tenant_id")
        doc_id       = event.get("document_id", "unknown")
        exc_type     = event.get("exception_type", "PROCESSING_EXCEPTION")

        rows = await conn.fetch(
            "SELECT oa_user_id, email FROM oa_user "
            "WHERE tenant_id=$1 AND role='oa_admin' AND status='ACTIVE'",
            tenant_id,
        )
        template_data = {"document_id": doc_id, "exception_type": exc_type}
        for row in rows:
            await self._fan_out(
                template_id=NotificationTemplate.EXCEPTION_ALERT,
                tenant_id=tenant_id,
                recipient_id=str(row["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=row["email"],
                template_data=template_data,
                event_type="EXCEPTION_RAISED",
                conn=conn,
            )

    async def _handle_elevation(self, event: dict, conn: asyncpg.Connection, *, approved: bool) -> None:
        requestor_id = event.get("requestor_id")
        tenant_id    = event.get("tenant_id")
        if not requestor_id:
            return

        row = await conn.fetchrow(
            "SELECT email FROM oa_user WHERE oa_user_id = $1", requestor_id
        )
        if not row:
            return

        template_id   = (NotificationTemplate.ELEVATION_APPROVED if approved
                          else NotificationTemplate.ELEVATION_DENIED)
        template_data = {"duration_hours": event.get("duration_hours", "")} if approved else {}
        event_type    = "ELEVATION_APPROVED" if approved else "ELEVATION_DENIED"

        await self._fan_out(
            template_id=template_id,
            tenant_id=tenant_id,
            recipient_id=requestor_id,
            recipient_type=RecipientType.OA_USER,
            recipient_email=row["email"],
            template_data=template_data,
            event_type=event_type,
            conn=conn,
        )

    async def _handle_welcome(self, event: dict, etype: str, conn: asyncpg.Connection) -> None:
        """TENANT_PROVISIONED only — the first OA-Admin's welcome email. (OA_USER_CREATED's
        welcome email is a separate, already-working path owned by OAUserConsumer's own
        direct notify_email() call; it never reaches this handler.)"""
        recipient = event.get("admin_email") or event.get("email")
        login_url = event.get("login_url", "https://prana.in/org/login")
        recipient_id = event.get("oa_user_id") or event.get("admin_id") or "unknown"
        tenant_id = event.get("tenant_id")
        if not recipient:
            return

        # Temp password is NOT stored in template_data — it was sent in the event
        # but we log the notification without it to preserve privacy
        await self._fan_out(
            template_id=NotificationTemplate.OA_WELCOME,
            tenant_id=tenant_id,
            recipient_id=str(recipient_id),
            recipient_type=RecipientType.OA_USER,
            recipient_email=recipient,
            template_data={"login_url": login_url},
            event_type=etype,
            conn=conn,
        )

    async def _handle_employee_welcome(self, event: dict, etype: str, conn: asyncpg.Connection) -> None:
        """VAULT_WELCOME/VAULT_WELCOME_REJOIN (workflows/employee_lifecycle.py's
        send_vault_welcome) and EMPLOYEE_CREDENTIALS_ISSUED (routers/employees.py) —
        mobile is decrypted via the platform auth CMK. One _fan_out() call carries
        both recipient_email and recipient_phone (whichever is present); each
        channel consumer already no-ops if its own required field is missing, so
        this naturally matches the old per-channel-guarded behaviour."""
        emp_id    = event.get("recipient_id") or event.get("employee_user_id")
        tenant_id = event.get("tenant_id")
        if not emp_id:
            return

        row = await conn.fetchrow(
            "SELECT enc_mobile, email FROM employee_user WHERE employee_user_id = $1", emp_id
        )
        mobile = self._decrypt_mobile(row["enc_mobile"]) if row else None
        if not row or (not mobile and not row["email"]):
            log.warning("%s: no delivery channel for employee_user_id=%s", etype, emp_id)
            return

        # etype is one of the 3 values this handler is dispatched for (see
        # _dispatch's "in (...)" check above) — all 3 are real NotificationTemplate
        # members, so this doubles as a defensive validation of that invariant.
        template_id = NotificationTemplate(etype)

        await self._fan_out(
            template_id=template_id,
            tenant_id=tenant_id,
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_phone=mobile,
            recipient_email=row["email"],
            template_data={},
            event_type=etype,
            conn=conn,
        )

    async def _handle_account_locked(self, event: dict, conn: asyncpg.Connection) -> None:
        tenant_id   = event.get("tenant_id")
        locked_user = event.get("locked_user_email", "")
        lock_reason = event.get("lock_reason", "POLICY_VIOLATION")
        template_data = {"locked_user_email": locked_user, "lock_reason": lock_reason}

        ciso = await self._lookup_ciso(conn, tenant_id)
        if ciso:
            await self._fan_out(
                template_id=NotificationTemplate.ACCOUNT_LOCKED,
                tenant_id=tenant_id,
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso["email"],
                template_data=template_data,
                event_type="ACCOUNT_LOCKED",
                conn=conn,
            )

    async def _handle_cross_tenant_upload(self, event: dict, conn: asyncpg.Connection) -> None:
        tenant_id      = event.get("tenant_id")        # uploading tenant (Tenant A)
        document_id    = event.get("document_id", "unknown")
        anomaly_id     = event.get("anomaly_id", "")
        owner_tenant   = event.get("owner_tenant_id", "unknown")
        template_data  = {
            "document_id":    document_id,
            "anomaly_id":     anomaly_id,
            "owner_tenant_id": owner_tenant,
        }

        # Notify Tenant A's CISO
        ciso = await self._lookup_ciso(conn, tenant_id)
        if ciso:
            await self._fan_out(
                template_id=NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT,
                tenant_id=tenant_id,
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso["email"],
                template_data=template_data,
                event_type="CROSS_TENANT_UPLOAD",
                conn=conn,
            )

        # Notify all active PA Admins (platform-level alert)
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await self._fan_out(
                template_id=NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT,
                tenant_id=tenant_id,
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                template_data=template_data,
                event_type="CROSS_TENANT_UPLOAD",
                conn=conn,
            )

    async def _handle_audit_integrity_mismatch(self, event: dict, conn: asyncpg.Connection) -> None:
        """Platform-level alert — spans potentially any tenant, so every active
        PA Admin is notified rather than a single tenant's CISO."""
        template_data = {
            "checked_count":     event.get("checked_count", 0),
            "mismatched_count":  event.get("mismatched_count", 0),
            "unverified_count":  event.get("unverified_count", 0),
        }
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await self._fan_out(
                template_id=NotificationTemplate.AUDIT_INTEGRITY_MISMATCH,
                tenant_id=None,
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                template_data=template_data,
                event_type="AUDIT_INTEGRITY_MISMATCH",
                conn=conn,
            )

    async def _handle_storage_expansion_requested(self, event: dict, conn: asyncpg.Connection) -> None:
        """Human-in-the-loop signal StorageExpansionWorkflow (Pattern 5) waits on —
        every active PA Admin is notified so any of them can approve/reject."""
        template_data = {
            "tenant_id":    event.get("tenant_id"),
            "request_id":   event.get("request_id"),
            "current_gb":   event.get("current_gb"),
            "requested_gb": event.get("requested_gb"),
        }
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await self._fan_out(
                template_id=NotificationTemplate.STORAGE_EXPANSION_REQUESTED,
                tenant_id=event.get("tenant_id"),
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                template_data=template_data,
                event_type="STORAGE_EXPANSION_REQUESTED",
                conn=conn,
            )

    async def _handle_onboarding_review_sla_breach(self, event: dict, conn: asyncpg.Connection) -> None:
        """OnboardingReviewSLAWorkflow's SLA timer expired with no PA decision —
        escalate to every active PA Admin, not just whoever was originally assigned."""
        template_data = {"tenant_id": event.get("tenant_id")}
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await self._fan_out(
                template_id=NotificationTemplate.ONBOARDING_REVIEW_SLA_BREACH,
                tenant_id=event.get("tenant_id"),
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                template_data=template_data,
                event_type="ONBOARDING_REVIEW_SLA_BREACH",
                conn=conn,
            )

    async def _handle_dpdp_employee(self, event: dict, conn: asyncpg.Connection, *, template_id: str) -> None:
        emp_id    = event.get("employee_user_id")
        tenant_id = event.get("tenant_id")
        if not emp_id:
            return

        row = await conn.fetchrow(
            "SELECT email FROM employee_user WHERE employee_user_id = $1", emp_id
        )
        if not row or not row["email"]:
            return

        await self._fan_out(
            template_id=template_id,
            tenant_id=tenant_id,
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_email=row["email"],
            template_data={},
            event_type=event.get("event_type", "DPDP"),
            conn=conn,
        )

    # -----------------------------------------------------------------------
    # DB helpers
    # -----------------------------------------------------------------------

    async def _lookup_ciso(self, conn: asyncpg.Connection, tenant_id: Optional[str]):
        if not tenant_id:
            return None
        return await conn.fetchrow(
            "SELECT oa_user_id, email FROM oa_user "
            "WHERE tenant_id=$1 AND role='ciso' AND status='ACTIVE' LIMIT 1",
            tenant_id,
        )
