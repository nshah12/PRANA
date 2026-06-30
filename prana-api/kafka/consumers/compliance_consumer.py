"""
ComplianceConsumer — prana.compliance.events

Starts the correct Temporal workflow for every DPDP Act 2023 action.
Previously DPDP events were incorrectly routed through prana.ingest.events;
this consumer owns the compliance topic exclusively.

Events handled:
  CONSENT_WITHDRAWN         → ConsentWithdrawalWorkflow
  ERASURE_REQUESTED         → ErasureConfirmationWorkflow
  DATA_EXPORT_REQUESTED     → DataExportWorkflow
  DATA_CORRECTION_REQUESTED → CorrectionWorkflow
  GRIEVANCE_FILED           → GrievanceWorkflow
  LEGAL_HOLD_APPLIED        → (no workflow — audit only, DB flag already set by router)
  LEGAL_HOLD_RELEASED       → (same)
"""
import json
from messages import SuccessCode, success_response
import logging
from typing import Optional

from aiokafka import AIOKafkaConsumer

from config import Settings
from kafka.producer import get_kafka_producer

log = logging.getLogger(__name__)
GROUP_ID = "prana-compliance-consumer"


class ComplianceConsumer:
    def __init__(self, settings: Settings, temporal_client=None) -> None:
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.compliance.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("ComplianceConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("ComplianceConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        uid = event.get("employee_user_id")
        tid = event.get("tenant_id")

        if etype == "CONSENT_WITHDRAWN":
            if self._temporal:
                await self._start(
                    workflow="ConsentWithdrawalWorkflow",
                    wf_id=f"consent-withdrawal-{uid}-{event.get('purpose','all')}",
                    args=[event],
                    task_queue="prana-compliance",
                )
            # WhatsApp confirmation — immediate channel for consent actions
            await self._notify("whatsapp", uid, tid, "CONSENT_WITHDRAWN",
                               {"purpose": event.get("purpose")})

        elif etype == "ERASURE_REQUESTED":
            if self._temporal:
                await self._start(
                    workflow="ErasureConfirmationWorkflow",
                    wf_id=f"erasure-{uid}",
                    args=[event],
                    task_queue="prana-compliance",
                )
            # Email confirmation of erasure request (DPDP mandated acknowledgement)
            await self._notify("email", uid, tid, "ERASURE_REQUESTED",
                               {"cancel_before_days": 30})
            # SMS quick alert
            await self._notify("sms", uid, tid, "ERASURE_REQUESTED",
                               {"cancel_before_days": 30})

        elif etype == "DATA_EXPORT_REQUESTED":
            if self._temporal:
                await self._start(
                    workflow="DataExportWorkflow",
                    wf_id=f"export-{event.get('export_id', uid)}",
                    args=[event],
                    task_queue="prana-compliance",
                )
            # Push notification — export can take time; push when ready isn't here yet
            await self._notify("push", uid, tid, "DATA_EXPORT_REQUESTED",
                               {"message": SuccessCode.EXPORT_REQUESTED})

        elif etype in ("CORRECTION_REQUESTED", "DATA_CORRECTION_REQUESTED"):
            if self._temporal:
                await self._start(
                    workflow="CorrectionWorkflow",
                    wf_id=f"correction-{event.get('correction_id', uid)}",
                    args=[event],
                    task_queue="prana-compliance",
                )

        elif etype == "GRIEVANCE_FILED":
            if self._temporal:
                await self._start(
                    workflow="GrievanceWorkflow",
                    wf_id=f"grievance-{event.get('grievance_id', uid)}",
                    args=[event],
                    task_queue="prana-compliance",
                )
            # Email acknowledgement — DPDP Act 2023 requires 48-hour ack
            await self._notify("email", uid, tid, "GRIEVANCE_FILED",
                               {"subject": event.get("subject"), "sla_days": 30})

        else:
            log.debug("ComplianceConsumer: no workflow for event_type=%s — audit sink handles it", etype)

    async def _notify(self, channel: str, recipient_id: Optional[str], tenant_id: Optional[str],
                      event_type: str, payload: dict) -> None:
        try:
            kafka = await get_kafka_producer()
            notif = {
                "event_type":   event_type,
                "recipient_id": recipient_id,
                "template_id":  event_type,
                "tenant_id":    tenant_id,
                "payload":      payload,
            }
            dispatch = {
                "email":     kafka.notify_email,
                "sms":       kafka.notify_sms,
                "push":      kafka.notify_push,
                "whatsapp":  kafka.notify_whatsapp,
                "bell":      kafka.notify_bell,
            }.get(channel)
            if dispatch:
                await dispatch(notif)
        except Exception:
            log.exception("ComplianceConsumer: failed to publish %s notification channel=%s", event_type, channel)

    async def _start(self, *, workflow: str, wf_id: str, args: list, task_queue: str) -> None:
        try:
            await self._temporal.start_workflow(
                workflow,
                args[0],
                id=wf_id,
                task_queue=task_queue,
            )
            log.info("ComplianceConsumer started %s workflow_id=%s", workflow, wf_id)
        except Exception as exc:
            if "already exists" in str(exc).lower():
                log.info("ComplianceConsumer: workflow already running workflow_id=%s", wf_id)
            else:
                log.exception("ComplianceConsumer: failed to start %s workflow_id=%s", workflow, wf_id)
                raise
