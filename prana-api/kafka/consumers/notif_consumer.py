"""
NotifConsumer — prana.notifications

Dispatches transactional notifications via NotificationService and
auto-creates incidents via IncidentService for P0/P1 anomalies.

Events handled:
  ANOMALY_DETECTED    → notify CISO (email+bell for P0/P1; bell for P2; nothing for P3)
                        auto-create incident for P0/P1
  DOC_ROUTED          → notify employee (push/WhatsApp/SMS cascade)
  EXCEPTION_RAISED    → notify OA-Admin (email + bell)
  ELEVATION_APPROVED  → notify OA-Operator (email)
  ELEVATION_DENIED    → notify OA-Operator (email)
  OA_USER_CREATED     → welcome email with temp password
  TENANT_PROVISIONED  → welcome email for first OA-Admin
  ACCOUNT_LOCKED      → notify CISO + OA-Admin (email + bell)
  CROSS_TENANT_UPLOAD → notify Tenant CISO (email + bell) + PA Admin (email)
  DPDP_ERASURE_DONE   → notify employee (email)
  DPDP_EXPORT_READY   → notify employee (email)
  DIGEST_READY        → notify role recipients (email)
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from services.notification_service import NotificationService, Channel, RecipientType
from services.incident_service import IncidentService

log = logging.getLogger(__name__)

GROUP_ID = "prana-notif-consumer"


class NotifConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None) -> None:
        self._settings = settings
        self._db_pool = db_pool
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
                        svc   = NotificationService(db=conn)
                        isvc  = IncidentService(db=conn)
                        await self._dispatch(event, etype, svc, isvc, conn)
                except Exception:
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
        elif etype in ("OA_USER_CREATED", "TENANT_PROVISIONED"):
            await self._handle_welcome(event, svc)
        elif etype == "ACCOUNT_LOCKED":
            await self._handle_account_locked(event, svc, conn)
        elif etype == "CROSS_TENANT_UPLOAD":
            await self._handle_cross_tenant_upload(event, svc, conn)
        elif etype == "DPDP_ERASURE_DONE":
            await self._handle_dpdp_employee(event, svc, conn, template_id="ERASURE_COMPLETE")
        elif etype == "DPDP_EXPORT_READY":
            await self._handle_dpdp_employee(event, svc, conn, template_id="EXPORT_READY")
        elif etype == "DIGEST_READY":
            await self._handle_digest_ready(event, svc, conn)
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
        severity    = event.get("severity", "P2")

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

    async def _handle_doc_routed(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        emp_id   = event.get("employee_user_id")
        doc_type = event.get("doc_type", "document")
        tenant_id = event.get("tenant_id")
        if not emp_id:
            return

        row = await conn.fetchrow(
            "SELECT email, phone FROM employee_user WHERE employee_user_id = $1", emp_id
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
            template_id="DOC_ROUTED",
            template_data={"doc_type": doc_type},
        )
        # WhatsApp cascade
        await svc.notify(
            tenant_id=tenant_id,
            event_type="DOC_ROUTED",
            recipient_id=emp_id,
            recipient_type=RecipientType.EMPLOYEE,
            recipient_phone=row["phone"],
            channel=Channel.WHATSAPP,
            template_id="DOC_ROUTED",
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
                template_id="EXCEPTION_ALERT",
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="EXCEPTION_RAISED",
                recipient_id=str(row["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id="EXCEPTION_ALERT",
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

        template_id   = "ELEVATION_APPROVED" if approved else "ELEVATION_DENIED"
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

    async def _handle_welcome(self, event: dict, svc: NotificationService) -> None:
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
            event_type="OA_USER_CREATED",
            recipient_id=str(recipient_id),
            recipient_type=RecipientType.OA_USER,
            recipient_email=recipient,
            channel=Channel.EMAIL,
            template_id="OA_WELCOME",
            template_data={"login_url": login_url},
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
                template_id="ACCOUNT_LOCKED",
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="ACCOUNT_LOCKED",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id="ACCOUNT_LOCKED",
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
                template_id="CROSS_TENANT_UPLOAD_ALERT",
                template_data=template_data,
            )
            await svc.notify(
                tenant_id=tenant_id,
                event_type="CROSS_TENANT_UPLOAD",
                recipient_id=str(ciso["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                channel=Channel.PORTAL_BELL,
                template_id="CROSS_TENANT_UPLOAD_ALERT",
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
                template_id="CROSS_TENANT_UPLOAD_ALERT",
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

    async def _handle_digest_ready(
        self, event: dict, svc: NotificationService, conn: asyncpg.Connection
    ) -> None:
        tenant_id = event.get("tenant_id")
        role      = event.get("role")            # chro / cfo / ciso
        period    = event.get("period", "weekly")

        if not role or not tenant_id:
            return

        rows = await conn.fetch(
            "SELECT oa_user_id, email FROM oa_user "
            "WHERE tenant_id=$1 AND role=$2 AND status='ACTIVE'",
            tenant_id, role,
        )
        for row in rows:
            await svc.notify(
                tenant_id=tenant_id,
                event_type="DIGEST_READY",
                recipient_id=str(row["oa_user_id"]),
                recipient_type=RecipientType.OA_USER,
                recipient_email=row["email"],
                channel=Channel.EMAIL,
                template_id="DIGEST_WEEKLY",
                template_data={"period": period},
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
