"""
Kafka producer — thin wrapper around aiokafka.AIOKafkaProducer.

One instance per process, held on app.state.kafka_producer.
All events serialised as UTF-8 JSON.

Partition strategy:
  - prana.ingest.events   → partition by tenant_id  (ingest ordering per tenant)
  - prana.pipeline.events → partition by document_id (all stage changes in order)
  - prana.audit.events    → partition by tenant_id
  - prana.notifications   → partition by user_id
  - prana.analytics.events→ partition by tenant_id
"""
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from config import Settings

log = logging.getLogger(__name__)

TOPIC_INGEST       = "prana.ingest.events"
TOPIC_PIPELINE     = "prana.pipeline.events"
TOPIC_AUDIT        = "prana.audit.events"
TOPIC_NOTIF        = "prana.notifications"
TOPIC_ANALYTICS    = "prana.analytics.events"
TOPIC_VAULT        = "prana.vault.events"
TOPIC_AUTH         = "prana.auth.events"
TOPIC_EMPLOYEE     = "prana.employee.events"
TOPIC_TENANT       = "prana.tenant.events"
TOPIC_OA_USERS     = "prana.oa_users.events"
TOPIC_COMPLIANCE   = "prana.compliance.events"
TOPIC_SECURITY     = "prana.security.events"
TOPIC_STATUTORY    = "prana.statutory.events"
TOPIC_INTEGRATIONS = "prana.integrations.events"
TOPIC_PLATFORM     = "prana.platform.events"
TOPIC_CACHE_INVAL  = "prana.cache.invalidation"

# Notification channel topics (split by delivery mechanism)
TOPIC_NOTIF_EMAIL    = "prana.notifications.email"
TOPIC_NOTIF_SMS      = "prana.notifications.sms"
TOPIC_NOTIF_PUSH     = "prana.notifications.push"
TOPIC_NOTIF_WA       = "prana.notifications.whatsapp"
TOPIC_NOTIF_BELL     = "prana.notifications.portal_bell"


class KafkaPub:
    """Async Kafka producer. Start/stop managed by FastAPI lifespan."""

    def __init__(self, settings: Settings) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            acks="all",
            compression_type="gzip",
            enable_idempotence=True,
            max_batch_size=16384,
        )

    async def start(self) -> None:
        await self._producer.start()
        log.info("KafkaPub started")

    async def stop(self) -> None:
        await self._producer.stop()
        log.info("KafkaPub stopped")

    async def publish(self, topic: str, event: dict[str, Any], *, key: str | None = None) -> None:
        try:
            await self._producer.send_and_wait(topic, value=event, key=key)
        except KafkaError:
            log.exception("Kafka publish failed topic=%s event_type=%s", topic, event.get("event_type"))
            raise

    # ── Domain helpers ────────────────────────────────────────────────────────

    async def doc_ingested(self, event: dict) -> None:
        await self.publish(TOPIC_INGEST, event, key=event["tenant_id"])
        await self.publish(TOPIC_AUDIT,  event, key=event["tenant_id"])

    async def batch_uploaded(self, event: dict) -> None:
        await self.publish(TOPIC_INGEST, event, key=event["tenant_id"])
        await self.publish(TOPIC_AUDIT,  event, key=event["tenant_id"])

    async def stage_changed(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,    event, key=event["tenant_id"])

    async def doc_routed(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE,  event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,     event, key=event["tenant_id"])
        await self.publish(TOPIC_ANALYTICS, event, key=event["tenant_id"])
        await self.publish(TOPIC_NOTIF,     event, key=event.get("employee_uuid", event["tenant_id"]))

    async def exception_raised(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,    event, key=event["tenant_id"])
        await self.publish(TOPIC_NOTIF,    event, key=event["tenant_id"])

    async def exception_resolved(self, event: dict) -> None:
        await self.publish(TOPIC_PIPELINE, event, key=event["document_id"])
        await self.publish(TOPIC_AUDIT,    event, key=event["tenant_id"])

    # ── Vault events ──────────────────────────────────────────────────────────

    async def doc_accessed(self, event: dict) -> None:
        """DOC_ACCESSED / SHARE_ACCESSED — AuditConsumer writes document_access_log async."""
        await self.publish(TOPIC_VAULT,     event, key=event.get("employee_uuid", event.get("tenant_id")))
        await self.publish(TOPIC_AUDIT,     event, key=event.get("tenant_id"))
        await self.publish(TOPIC_ANALYTICS, event, key=event.get("tenant_id"))

    async def share_event(self, event: dict) -> None:
        """SHARE_CREATED / SHARE_REVOKED / SHARE_EXPIRED / SHARE_OTP_* events."""
        await self.publish(TOPIC_VAULT,  event, key=event.get("employee_uuid", event.get("tenant_id")))
        await self.publish(TOPIC_AUDIT,  event, key=event.get("tenant_id"))

    # ── Auth events ───────────────────────────────────────────────────────────

    async def auth_event(self, event: dict) -> None:
        """SESSION_CREATED, LOGIN_SUCCESS, LOGIN_FAILED, TOTP_*, OTP_* events."""
        await self.publish(TOPIC_AUTH,   event, key=event.get("user_id", event.get("tenant_id")))
        await self.publish(TOPIC_AUDIT,  event, key=event.get("tenant_id"))

    # ── Employee lifecycle events ─────────────────────────────────────────────

    async def employee_event(self, event: dict) -> None:
        """EMPLOYEE_ONBOARDED, ACTIVATED, EXITED, REJOINED, VAULT_ACTIVATED, etc."""
        await self.publish(TOPIC_EMPLOYEE,  event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,     event, key=event.get("tenant_id"))

    # ── Tenant events ─────────────────────────────────────────────────────────

    async def tenant_event(self, event: dict) -> None:
        """TENANT_CREATED, CONFIG_UPDATED, API_KEY_CREATED/REVOKED, KEK_ROTATED, etc."""
        await self.publish(TOPIC_TENANT,    event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,     event, key=event.get("tenant_id"))
        # Trigger cache invalidation for config/apikey changes
        etype = event.get("event_type", "")
        if etype in ("TENANT_CONFIG_UPDATED",):
            await self.cache_invalidate("CONFIG_INVALIDATE", tenant_id=event.get("tenant_id"))
        elif etype in ("API_KEY_REVOKED",):
            await self.cache_invalidate("APIKEY_INVALIDATE",
                                        key_hash=event.get("key_hash"),
                                        tenant_id=event.get("tenant_id"))

    # ── OA user events ────────────────────────────────────────────────────────

    async def oa_user_event(self, event: dict) -> None:
        """OA_USER_CREATED, LOCKED, ELEVATION_APPROVED/DENIED/EXPIRED, etc."""
        await self.publish(TOPIC_OA_USERS, event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,    event, key=event.get("tenant_id"))
        # Invalidate OA permissions cache on role/elevation changes
        oa_user_id = event.get("oa_user_id")
        if oa_user_id:
            await self.cache_invalidate("OA_PERMISSIONS_INVALIDATE", oa_user_id=oa_user_id,
                                        tenant_id=event.get("tenant_id"))

    # ── Compliance / DPDP events ──────────────────────────────────────────────

    async def compliance_event(self, event: dict) -> None:
        """CONSENT_GRANTED/WITHDRAWN, ERASURE_*, CORRECTION_*, GRIEVANCE_*, etc."""
        await self.publish(TOPIC_COMPLIANCE, event, key=event.get("employee_user_id", event.get("tenant_id")))
        await self.publish(TOPIC_AUDIT,      event, key=event.get("tenant_id"))

    # ── Security events ───────────────────────────────────────────────────────

    async def security_event(self, event: dict) -> None:
        """ANOMALY_DETECTED, ACCOUNT_LOCKED, CROSS_TENANT_UPLOAD, CSAM_DETECTED, etc."""
        await self.publish(TOPIC_SECURITY, event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,    event, key=event.get("tenant_id"))
        await self.publish(TOPIC_NOTIF,    event, key=event.get("tenant_id"))

    # ── Statutory / labour law events ────────────────────────────────────────

    async def statutory_event(self, event: dict) -> None:
        """OBLIGATION_DUE, OBLIGATION_OVERDUE, PF_FILING_DUE, GRATUITY_*, etc."""
        await self.publish(TOPIC_STATUTORY, event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,     event, key=event.get("tenant_id"))

    # ── Integration events ────────────────────────────────────────────────────

    async def integration_event(self, event: dict) -> None:
        """HRMS_WEBHOOK_*, EPFO_VERIFICATION_*, KMS_*, TEXTRACT_*, etc."""
        await self.publish(TOPIC_INTEGRATIONS, event, key=event.get("tenant_id"))
        await self.publish(TOPIC_AUDIT,        event, key=event.get("tenant_id"))

    # ── Platform / ops events ─────────────────────────────────────────────────

    async def platform_event(self, event: dict) -> None:
        """WORKER_STARTED/CRASHED, HEALTH_CHECK_FAILED, DEPLOYMENT_*, etc."""
        await self.publish(TOPIC_PLATFORM, event, key=event.get("service", "platform"))

    # ── Cache invalidation ────────────────────────────────────────────────────

    async def cache_invalidate(self, event_type: str, **kwargs) -> None:
        """Publish a cache invalidation event. All pods consume and DEL their keys."""
        event = {"event_type": event_type, **kwargs}
        await self.publish(TOPIC_CACHE_INVAL, event, key=kwargs.get("tenant_id", "global"))

    # ── Split notification helpers ────────────────────────────────────────────

    async def notify_email(self, event: dict) -> None:
        await self.publish(TOPIC_NOTIF_EMAIL, event, key=event.get("recipient_id", event.get("tenant_id")))

    async def notify_sms(self, event: dict) -> None:
        await self.publish(TOPIC_NOTIF_SMS, event, key=event.get("recipient_id", event.get("tenant_id")))

    async def notify_push(self, event: dict) -> None:
        await self.publish(TOPIC_NOTIF_PUSH, event, key=event.get("recipient_id", event.get("tenant_id")))

    async def notify_whatsapp(self, event: dict) -> None:
        await self.publish(TOPIC_NOTIF_WA, event, key=event.get("recipient_id", event.get("tenant_id")))

    async def notify_bell(self, event: dict) -> None:
        await self.publish(TOPIC_NOTIF_BELL, event, key=event.get("recipient_id", event.get("tenant_id")))


# ── Module-level factory (used by Temporal activities outside app lifecycle) ──

_kafka_producer: "KafkaPub | None" = None


def set_kafka_producer(producer: "KafkaPub") -> None:
    """Called from FastAPI lifespan after producer.start() so activities can access it."""
    global _kafka_producer
    _kafka_producer = producer


async def get_kafka_producer() -> "KafkaPub":
    """Return the module-level KafkaPub. Raises if not yet initialised."""
    if _kafka_producer is None:
        raise RuntimeError(
            "Kafka producer not initialised. "
            "Call set_kafka_producer() during app startup before using activities."
        )
    return _kafka_producer
