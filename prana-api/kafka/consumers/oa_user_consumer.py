"""
OAUserConsumer — prana.oa_users.events

Handles OA user lifecycle and elevation events.
Elevation workflow start was previously done directly in the HTTP handler;
that remains for the initial ElevationWorkflow start (direct Temporal call in HTTP is allowed
for signal-correlated workflows). This consumer handles everything else:
notifications, cache invalidation side-effects, audit-driven workflows.

Events handled:
  OA_USER_CREATED          → trigger welcome email notification
  OA_USER_LOCKED           → start PolicyLockWorkflow
  ELEVATION_REQUESTED      → audit (workflow already started in HTTP handler)
  ELEVATION_APPROVED       → no action here — kafka.oa_user_event() dual-publishes
                              this to TOPIC_NOTIF, where CommunicationHubConsumer._handle_elevation
                              (resolves oa_user.email) sends the email
  ELEVATION_DENIED         → same as above
  ELEVATION_EXPIRED        → requests notification for the requestor via
                              kafka.communication_requested() — CommunicationHubConsumer
                              resolves the channel(s) via notification_channel_policy
                              (portal_bell by default) and fans out
  ROLE_CHANGED             → audit (fanned out to prana.audit.events by
                              kafka.oa_user_event() already — nothing to do here for
                              that part) + PRIVILEGE_ESCALATION detection: publishes
                              ANOMALY_DETECTED to prana.security.events so
                              SecurityConsumer persists anomaly_event + creates an
                              incident, same pipeline as every other anomaly source.
                              See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.1.
"""
import json
import logging
import uuid
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import get_kafka_producer

log = logging.getLogger(__name__)
GROUP_ID = "prana-oa-user-consumer"

# oa_operator < specialist roles (chro/cfo/ciso) < oa_admin. Used only to decide
# whether a role change is an ESCALATION (jump to a higher rank) — not a general
# ranking of role importance.
_ROLE_RANK = {"oa_operator": 1, "chro": 2, "cfo": 2, "ciso": 2, "oa_admin": 3}


class OAUserConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.oa_users.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("OAUserConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="OAUserConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("OAUserConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype in ("OA_USER_CREATED", "OA_WELCOME_RESENT"):
            await self._notify_welcome(event)

        elif etype == "OA_USER_LOCKED":
            if self._temporal:
                oa_user_id = event.get("oa_user_id")
                wf_id = f"account-lock-oa-{oa_user_id}"
                try:
                    # "AccountLockWorkflow" was never @workflow.defn'd anywhere — the
                    # real generic policy-lock workflow is PolicyLockWorkflow
                    # (workflows/security.py), registered on secops-queue in worker.py,
                    # backed by AccountLockService.apply_policy_lock which expects
                    # user_type/user_id/tenant_id/reason_code, not the raw event shape.
                    await self._temporal.start_workflow(
                        "PolicyLockWorkflow",
                        {"user_type": "oa_user", "user_id": oa_user_id,
                         "tenant_id": event.get("tenant_id"),
                         "reason_code": event.get("reason_code", "OA_ADMIN_LOCK")},
                        id=wf_id,
                        task_queue="secops-queue",
                    )
                    log.info("OAUserConsumer: started PolicyLockWorkflow workflow_id=%s", wf_id)
                except Exception as exc:
                    if "already exists" not in str(exc).lower():
                        log.exception("OAUserConsumer: failed to start PolicyLockWorkflow")

        elif etype == "ELEVATION_EXPIRED":
            await self._notify_elevation_expired(event)

        elif etype in ("ELEVATION_APPROVED", "ELEVATION_DENIED"):
            # No email here — kafka.oa_user_event() dual-publishes these two event
            # types to TOPIC_NOTIF, where CommunicationHubConsumer._handle_elevation (already
            # correct: resolves oa_user.email, uses template_data) owns the send.
            # Sending from both places would double-notify the requestor.
            log.debug("OAUserConsumer: %s email handled by CommunicationHubConsumer via TOPIC_NOTIF dual-publish", etype)

        elif etype == "ROLE_CHANGED":
            await self._detect_privilege_escalation(event)

        else:
            log.debug("OAUserConsumer: no action for event_type=%s", etype)

    async def _notify_welcome(self, event: dict) -> None:
        try:
            kafka = await get_kafka_producer()
            template_data = {"login_url": event.get("login_url", "https://prana.in/org/login")}
            setup_token = event.get("setup_token")
            if setup_token:
                # The only place this account's actual first password gets set —
                # POST /v1/org/users never returns/discloses the server-generated
                # temp password anywhere. The link, not a password, is what's emailed.
                template_data["setup_url"] = f"https://prana.in/org/set-password?token={setup_token}"
            await kafka.communication_requested({
                "event_type":    "OA_WELCOME",
                "recipient_id":  event.get("oa_user_id"),
                "recipient_type": "OA_USER",
                "recipient_email": event.get("email"),
                "template_id":   "OA_WELCOME",
                "tenant_id":     event.get("tenant_id"),
                "template_data": template_data,
            })
            log.info("OAUserConsumer: requested OA_WELCOME notification oa_user_id=%s", event.get("oa_user_id"))
        except Exception:
            log.exception("OAUserConsumer: failed to request OA_WELCOME notification")

    async def _detect_privilege_escalation(self, event: dict) -> None:
        old_role = event.get("old_role")
        new_role = event.get("new_role")
        actor_id = event.get("actor_id")
        target_id = event.get("oa_user_id")

        self_change = actor_id is not None and actor_id == target_id
        old_rank = _ROLE_RANK.get(old_role, 0)
        new_rank = _ROLE_RANK.get(new_role, 0)
        escalation = self_change or new_rank > old_rank
        if not escalation:
            return

        try:
            kafka = await get_kafka_producer()
            await kafka.security_event({
                "event_type": "ANOMALY_DETECTED",
                "anomaly_id": str(uuid.uuid4()),
                "rule_name": "PRIVILEGE_ESCALATION",
                "tenant_id": event.get("tenant_id"),
                "actor_id": actor_id,
                "event_metadata": {
                    "target_oa_user_id": target_id, "old_role": old_role, "new_role": new_role,
                    "self_change": self_change,
                },
            })
            log.warning(
                "OAUserConsumer: PRIVILEGE_ESCALATION flagged target=%s %s->%s self_change=%s",
                target_id, old_role, new_role, self_change,
            )
        except Exception:
            log.exception("OAUserConsumer: failed to publish PRIVILEGE_ESCALATION anomaly")

    async def _notify_elevation_expired(self, event: dict) -> None:
        recipient_id = event.get("requestor_id") or event.get("oa_user_id")
        template_data = {"elevation_id": event.get("elevation_id"), "duration_hours": event.get("duration_hours")}
        try:
            kafka = await get_kafka_producer()
            await kafka.communication_requested({
                "event_type":    "ELEVATION_EXPIRED",
                "recipient_id":  recipient_id,
                "recipient_type": "OA_USER",
                "template_id":   "ELEVATION_EXPIRED",
                "tenant_id":     event.get("tenant_id"),
                "template_data": template_data,
            })
            log.info("OAUserConsumer: requested ELEVATION_EXPIRED notification recipient=%s", recipient_id)
        except Exception:
            log.exception("OAUserConsumer: failed to request ELEVATION_EXPIRED notification")
