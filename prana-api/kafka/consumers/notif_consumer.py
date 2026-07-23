"""
NotifConsumer — prana.notifications

Dispatches transactional notifications via NotificationService and
auto-creates incidents via IncidentService for P0/P1 anomalies.

Events handled:
  ANOMALY_DETECTED    → notify CISO (email+bell for P0/P1; bell for P2; nothing for P3)
                        auto-create incident for P0/P1
  DOC_ROUTED          → notify employee (push/WhatsApp/SMS cascade)
  EXCEPTION_RAISED    → notify OA-Admin (email + bell)
  ELEVATION_APPROVED  → notify OA-Operator (email; kafka.oa_user_event() dual-
                        publishes this one to TOPIC_NOTIF too — ELEVATION_EXPIRED
                        stays bell-only, handled directly by OAUserConsumer)
  ELEVATION_DENIED    → notify OA-Operator (email; same dual-publish as above)
  TENANT_PROVISIONED  → welcome email for first OA-Admin (kafka.tenant_event()
                        dual-publishes this one event_type to TOPIC_NOTIF).
                        OA_USER_CREATED's welcome email is a SEPARATE path —
                        OAUserConsumer._notify_welcome publishes notify_email()
                        directly; it never reaches this consumer at all.
  ACCOUNT_LOCKED      → notify CISO + OA-Admin (email + bell)
  CROSS_TENANT_UPLOAD → notify Tenant CISO (email + bell) + PA Admin (email)
  DPDP_ERASURE_DONE   → notify employee (email)
  DPDP_EXPORT_READY   → notify employee (email)
  SHARE_ACCESSED      → notify employee/share-owner (email) — published by
                        workflows/vault_shares.py's notify_share_accessed activity
  AUDIT_INTEGRITY_MISMATCH → notify all active PA Admins (email) — platform-level,
                        raised by AuditIntegrityVerificationWorkflow when a
                        recent audit_event row no longer matches its Immudb
                        dual-write (see KAFKA_REDIS_ARCHITECTURE.md §8)
  VAULT_WELCOME / VAULT_WELCOME_REJOIN → notify employee their vault is active
                        (SMS to mobile + email if present) — published by
                        workflows/employee_lifecycle.py's send_vault_welcome activity
  EMPLOYEE_CREDENTIALS_ISSUED → notify employee an account now exists (SMS + email) —
                        published by routers/employees.py when create/import supplied
                        a mobile or email, so a temp password was actually generated
  STORAGE_EXPANSION_REQUESTED → notify all active PA Admins (email) — platform-level,
                        raised by PlatformOpsService.notify_storage_expansion_request;
                        this is the human-in-the-loop signal StorageExpansionWorkflow
                        (Pattern 5) is waiting on
  ONBOARDING_REVIEW_SLA_BREACH → notify all active PA Admins (email) — platform-level,
                        raised by PlatformOpsService.escalate_onboarding_review when
                        OnboardingReviewSLAWorkflow's SLA timer expires with no decision
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from messages import NotificationTemplate
from services.encryption_service import resolve_platform_auth_kek_arn
from services.notification_service import NotificationService, Channel, RecipientType
from services.incident_service import IncidentService

log = logging.getLogger(__name__)

GROUP_ID = "prana-notif-consumer"


class NotifConsumer:
    def __init__(
        self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None,
        kms_service=None, redis=None,
    ) -> None:
        self._settings = settings
        self._db_pool = db_pool
        self._kms = kms_service
        self._redis = redis
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
                    async with self._db_pool.acquire() as conn:
                        svc   = NotificationService(db=conn, settings=self._settings, redis_client=self._redis)
                        isvc  = IncidentService(db=conn)
                        await self._dispatch(event, etype, svc, isvc, conn)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._db_pool, consumer_name="NotifConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("NotifConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(
        self,
        event: dict,
        etype: Optional[str],
        svc: NotificationService,
        isvc: IncidentService,
        conn: asyncpg.Connection,
    ) -> None:
        if etype == "ANOMALY_DETECTED":
            await self._handle_anomaly(event, svc, isvc, conn)
        elif etype == "DOC_ROUTED":
            await self._handle_doc_routed(event, svc, conn)
        elif etype == "EXCEPTION_RAISED":
            await self._handle_exception(event, svc, conn)
        elif etype == "ELEVATION_APPROVED":
            await self._handle_elevation(event, svc, conn, approved=True)
        elif etype == "ELEVATION_DENIED":
            await self._handle_elevation(event, svc, conn, approved=False)
        elif etype == "TENANT_PROVISIONED":
            await self._handle_welcome(event, etype, svc)
        elif etype == "ACCOUNT_LOCKED":
            await self._handle_account_locked(event, svc, conn)
        elif etype == "CROSS_TENANT_UPLOAD":
            await self._handle_cross_tenant_upload(event, svc, conn)
        elif etype == "DPDP_ERASURE_DONE":
            await self._handle_dpdp_employee(event, svc, conn, template_id=NotificationTemplate.ERASURE_COMPLETE)
        elif etype == "DPDP_EXPORT_READY":
            await self._handle_dpdp_employee(event, svc, conn, template_id=NotificationTemplate.EXPORT_READY)
        elif etype == "SHARE_ACCESSED":
            await self._handle_dpdp_employee(event, svc, conn, template_id=NotificationTemplate.SHARE_ACCESSED)
        elif etype == "AUDIT_INTEGRITY_MISMATCH":
            await self._handle_audit_integrity_mismatch(event, svc, conn)
        elif etype in ("VAULT_WELCOME", "VAULT_WELCOME_REJOIN", "EMPLOYEE_CREDENTIALS_ISSUED"):
            await self._handle_employee_welcome(event, etype, svc, conn)
        elif etype == "STORAGE_EXPANSION_REQUESTED":
            await self._handle_storage_expansion_requested(event, svc, conn)
        elif etype == "ONBOARDING_REVIEW_SLA_BREACH":
            await self._handle_onboarding_review_sla_breach(event, svc, conn)
        else:
            log.debug("NotifConsumer: unhandled event_type=%s", etype)

    # -----------------------------------------------------------------------
    # Handlers
    # -----------------------------------------------------------------------

    async def _handle_anomaly(
        self,
        event: dict,
        svc: NotificationService,
        isvc: IncidentService,
        conn: asyncpg.Connection,
    ) -> None:
        tenant_id   = event.get("tenant_id")
        anomaly_id  = event.get("anomaly_id")
        rule_name   = event.get("rule_name", "UNKNOWN")
        severity    = event.get("severity")
        if not severity:
            # Same shared policy lookup security_consumer.py uses — the two consumers
            # can no longer default to different severities for the same event. See
            # prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §4.
            from services.severity_policy_service import SeverityPolicyService
            severity = await SeverityPolicyService(conn).resolve_severity(
                domain="ANOMALY_RULE", value=rule_name,
            ) or "P3"

        ciso = await self._lookup_ciso(conn, tenant_id)
        if ciso:
            await svc.notify_anomaly(
                tenant_id=tenant_id,
                anomaly_id=anomaly_id,
                rule_name=rule_name,
                severity=severity,
                ciso_id=str(ciso["oa_user_id"]),
                ciso_email=ciso["email"],
            )

        # Auto-create incident for P0/P1
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

    async def _handle_doc_routed(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
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

        # Push notification (primary)
        await svc.notify(
            tenant_id=tenant_id,
            event_type="DOC_ROUTED",
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            channel=Channel.PUSH,
            template_id=NotificationTemplate.DOC_ROUTED,
            template_data={"doc_type": doc_type},
        )
        # WhatsApp cascade
        await svc.notify(
            tenant_id=tenant_id,
            event_type="DOC_ROUTED",
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_phone=self._decrypt_mobile(row["enc_mobile"]),
            channel=Channel.WHATSAPP,
            template_id=NotificationTemplate.DOC_ROUTED,
            template_data={"doc_type": doc_type},
        )

    async def _handle_exception(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
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
            await svc.notify(
                tenant_id=tenant_id,
                event_type="EXCEPTION_RAISED",
                recipient_id=str(row["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=row["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.EXCEPTION_ALERT,
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="EXCEPTION_RAISED",
                recipient_id=str(row["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id=NotificationTemplate.EXCEPTION_ALERT,
                template_data=template_data,
            )

    async def _handle_elevation(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection, *, approved: bool
    ) -> None:
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

        await svc.notify(
            tenant_id=tenant_id,
            event_type=event_type,
            recipient_id=requestor_id,
            recipient_type=RecipientType.OA_USER,
            recipient_email=row["email"],
            channel=Channel.EMAIL,
            template_id=template_id,
            template_data=template_data,
        )

    async def _handle_welcome(self, event: dict, etype: str, svc: NotificationService) -> None:
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
        await svc.notify(
            tenant_id=tenant_id,
            event_type=etype,
            recipient_id=str(recipient_id),
            recipient_type=RecipientType.OA_USER,
            recipient_email=recipient,
            channel=Channel.EMAIL,
            template_id=NotificationTemplate.OA_WELCOME,
            template_data={"login_url": login_url},
        )

    async def _handle_employee_welcome(
        self, event: dict, etype: str, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        """VAULT_WELCOME/VAULT_WELCOME_REJOIN (workflows/employee_lifecycle.py's
        send_vault_welcome, fired once a document is routed and the vault is
        activated) and EMPLOYEE_CREDENTIALS_ISSUED (routers/employees.py, fired at
        employee creation when the employer supplied a mobile/email) were both
        previously unhandled here — this method used to not exist at all, so every
        one of these events silently fell through to the `unhandled event_type`
        debug log with no notification ever sent. mobile is the employee's primary
        login handle (encrypted at rest as enc_mobile — decrypted here via the
        platform auth CMK, see .claude/rules/security.md), so SMS is tried
        first; email is a secondary/fallback channel sent in addition when present.
        Same as OA's _handle_welcome, the temp password itself is never put in
        template_data/notification_log — only that credentials now exist."""
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

        if mobile:
            await svc.notify(
                tenant_id=tenant_id,
                event_type=etype,
                recipient_id=emp_id,
                recipient_type=RecipientType.EMPLOYEE,
                recipient_phone=mobile,
                channel=Channel.SMS,
                template_id=template_id,
                template_data={},
            )
        if row["email"]:
            await svc.notify(
                tenant_id=tenant_id,
                event_type=etype,
                recipient_id=emp_id,
                recipient_type=RecipientType.EMPLOYEE,
                recipient_email=row["email"],
                channel=Channel.EMAIL,
                template_id=template_id,
                template_data={},
            )

    async def _handle_account_locked(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        tenant_id   = event.get("tenant_id")
        locked_user = event.get("locked_user_email", "")
        lock_reason = event.get("lock_reason", "POLICY_VIOLATION")
        template_data = {"locked_user_email": locked_user, "lock_reason": lock_reason}

        ciso = await self._lookup_ciso(conn, tenant_id)
        if ciso:
            await svc.notify(
                tenant_id=tenant_id,
                event_type="ACCOUNT_LOCKED",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.ACCOUNT_LOCKED,
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="ACCOUNT_LOCKED",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id=NotificationTemplate.ACCOUNT_LOCKED,
                template_data=template_data,
            )

    async def _handle_cross_tenant_upload(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        tenant_id      = event.get("tenant_id")        # uploading tenant (Tenant A)
        document_id    = event.get("document_id", "unknown")
        anomaly_id     = event.get("anomaly_id", "")
        owner_tenant   = event.get("owner_tenant_id", "unknown")
        template_data  = {
            "document_id":    document_id,
            "anomaly_id":     anomaly_id,
            "owner_tenant_id": owner_tenant,
        }

        # Notify Tenant A's CISO via email + portal bell
        ciso = await self._lookup_ciso(conn, tenant_id)
        if ciso:
            await svc.notify(
                tenant_id=tenant_id,
                event_type="CROSS_TENANT_UPLOAD",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=ciso["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT,
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="CROSS_TENANT_UPLOAD",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id=NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT,
                template_data=template_data,
            )

        # Notify all active PA Admins (platform-level alert)
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await svc.notify(
                tenant_id=tenant_id,
                event_type="CROSS_TENANT_UPLOAD",
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.CROSS_TENANT_UPLOAD_ALERT,
                template_data=template_data,
            )

    async def _handle_audit_integrity_mismatch(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
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
            await svc.notify(
                tenant_id=None,
                event_type="AUDIT_INTEGRITY_MISMATCH",
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.AUDIT_INTEGRITY_MISMATCH,
                template_data=template_data,
            )

    async def _handle_storage_expansion_requested(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
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
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type="STORAGE_EXPANSION_REQUESTED",
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.STORAGE_EXPANSION_REQUESTED,
                template_data=template_data,
            )

    async def _handle_onboarding_review_sla_breach(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        """OnboardingReviewSLAWorkflow's SLA timer expired with no PA decision —
        escalate to every active PA Admin, not just whoever was originally assigned."""
        template_data = {"tenant_id": event.get("tenant_id")}
        pa_admins = await conn.fetch(
            "SELECT pa_id, email FROM portal_admin WHERE status='ACTIVE'",
        )
        for pa in pa_admins:
            await svc.notify(
                tenant_id=event.get("tenant_id"),
                event_type="ONBOARDING_REVIEW_SLA_BREACH",
                recipient_id=str(pa["pa_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=pa["email"],
                channel=Channel.EMAIL,
                template_id=NotificationTemplate.ONBOARDING_REVIEW_SLA_BREACH,
                template_data=template_data,
            )

    async def _handle_dpdp_employee(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection, *, template_id: str
    ) -> None:
        emp_id    = event.get("employee_user_id")
        tenant_id = event.get("tenant_id")
        if not emp_id:
            return

        row = await conn.fetchrow(
            "SELECT email FROM employee_user WHERE employee_user_id = $1", emp_id
        )
        if not row or not row["email"]:
            return

        await svc.notify(
            tenant_id=tenant_id,
            event_type=event.get("event_type", "DPDP"),
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_email=row["email"],
            channel=Channel.EMAIL,
            template_id=template_id,
            template_data={},
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
