"""
DPDP Act 2023 compliance workflows — thin Temporal shells.
Business logic lives in services/compliance_service.py (zero Temporal imports).

Task queue: compliance-queue

Workflows:
  ErasureConfirmationWorkflow  — 30-day cooling-off, then purge all employee data
  ConsentRebumpWorkflow        — re-solicit consent after X days if not granted
  DataExportWorkflow           — package all employee data as encrypted ZIP
  GrievanceWorkflow            — track grievance → resolution within 30 days (DPDP mandate)
  DataCorrectionWorkflow       — employee-requested insight correction review
  RetentionWorkflow            — 7-year legal retention clock per document
  AuditArchivalWorkflow        — move audit events from hot DB to cold Iceberg on S3
  LegalHoldWorkflow            — freeze all deletions on a legal_hold_id scope
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

TASK_QUEUE = "compliance-queue"

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Activities (implementations in services/compliance_service.py) ─────────────

@activity.defn(name="send_erasure_notice")
async def send_erasure_notice(params: dict) -> None: ...

@activity.defn(name="execute_erasure")
async def execute_erasure(params: dict) -> None: ...

@activity.defn(name="send_consent_rebump")
async def send_consent_rebump(params: dict) -> None: ...

@activity.defn(name="check_consent_status")
async def check_consent_status(params: dict) -> dict: ...

@activity.defn(name="build_data_export")
async def build_data_export(params: dict) -> dict: ...

@activity.defn(name="notify_export_ready")
async def notify_export_ready(params: dict) -> None: ...

@activity.defn(name="open_grievance")
async def open_grievance(params: dict) -> None: ...

@activity.defn(name="escalate_grievance")
async def escalate_grievance(params: dict) -> None: ...

@activity.defn(name="close_grievance")
async def close_grievance(params: dict) -> None: ...

@activity.defn(name="apply_data_correction")
async def apply_data_correction(params: dict) -> None: ...

@activity.defn(name="notify_correction_complete")
async def notify_correction_complete(params: dict) -> None: ...

@activity.defn(name="schedule_document_deletion")
async def schedule_document_deletion(params: dict) -> None: ...

@activity.defn(name="archive_audit_events_batch")
async def archive_audit_events_batch(params: dict) -> dict: ...

@activity.defn(name="apply_legal_hold")
async def apply_legal_hold(params: dict) -> None: ...

@activity.defn(name="release_legal_hold")
async def release_legal_hold(params: dict) -> None: ...

@activity.defn(name="get_config_value")
async def get_config_value(params: dict) -> str: ...


# ── ErasureConfirmationWorkflow (Pattern 1 — Durable Timer + Pattern 2 — interruptible) ──

@workflow.defn(name="ErasureConfirmationWorkflow")
class ErasureConfirmationWorkflow:
    """
    Employee requests erasure → 30-day cooling-off window starts.
    During window: employee can cancel via 'cancel_erasure' signal.
    After 30 days with no cancellation: hard-delete all employee data.
    Duration from platform_config key 'dpdp_erasure_confirmation_days'.
    """

    def __init__(self):
        self._cancelled = False

    @workflow.signal(name="cancel_erasure")
    def cancel_erasure(self) -> None:
        self._cancelled = True

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        days_str = await workflow.execute_activity(
            get_config_value,
            {"key": "dpdp_erasure_confirmation_days",
             "tenant_id": params.get("tenant_id"), "default": "30"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.execute_activity(
            send_erasure_notice, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        cancelled = await workflow.wait_condition(
            lambda: self._cancelled, timeout=timedelta(days=int(days_str)),
        )
        if cancelled or self._cancelled:
            return
        await workflow.execute_activity(
            execute_erasure, params,
            start_to_close_timeout=timedelta(minutes=30), retry_policy=_RETRY,
        )


# ── ConsentRebumpWorkflow (Pattern 1 — Durable Timer) ─────────────────────────

@workflow.defn(name="ConsentRebumpWorkflow")
class ConsentRebumpWorkflow:
    """
    After consent_rebump_window_days, check if employee has granted consent.
    If not granted: send a reminder notification.
    Runs once per employee per consent window.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        days_str = await workflow.execute_activity(
            get_config_value,
            {"key": "consent_rebump_window_days",
             "tenant_id": params.get("tenant_id"), "default": "30"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.sleep(timedelta(days=int(days_str)))
        status = await workflow.execute_activity(
            check_consent_status, {"employee_user_id": params["employee_user_id"]},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        if not status.get("consent_granted"):
            await workflow.execute_activity(
                send_consent_rebump, params,
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )


# ── DataExportWorkflow (Pattern 1 — Durable Timer, fast) ──────────────────────

@workflow.defn(name="DataExportWorkflow")
class DataExportWorkflow:
    """
    Package all employee data (documents, events, audit log) into an
    encrypted ZIP on S3 and notify the employee with a time-limited download link.
    DPDP Act 2023 mandates delivery within 30 days; we target <24h.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            build_data_export,
            params,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=_RETRY,
        )

        await workflow.execute_activity(
            notify_export_ready,
            {**params, **result},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )

        return result


# ── GrievanceWorkflow (Pattern 5 — Human Signal) ──────────────────────────────

@workflow.defn(name="GrievanceWorkflow")
class GrievanceWorkflow:
    """
    Employee files a grievance → DPDP mandates resolution within 30 days.
    Waits for 'resolve_grievance' signal from ComplianceOfficer.
    If no signal within SLA: escalate to Platform Admin.
    """

    def __init__(self):
        self._resolved = False
        self._resolution_note: str = ""

    @workflow.signal(name="resolve_grievance")
    def resolve_grievance(self, payload: dict) -> None:
        self._resolved = True
        self._resolution_note = payload.get("note", "")

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        sla_str = await workflow.execute_activity(
            get_config_value,
            {"key": "grievance_sla_days", "tenant_id": params.get("tenant_id"), "default": "30"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.execute_activity(
            open_grievance, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        resolved = await workflow.wait_condition(
            lambda: self._resolved, timeout=timedelta(days=int(sla_str)),
        )
        if not resolved:
            await workflow.execute_activity(
                escalate_grievance, {**params, "reason": "SLA_BREACH"},
                start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
            )
            return
        await workflow.execute_activity(
            close_grievance, {**params, "note": self._resolution_note},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )


# ── DataCorrectionWorkflow (Pattern 5 — Human Signal) ────────────────────────

@workflow.defn(name="DataCorrectionWorkflow")
class DataCorrectionWorkflow:
    """
    Employee flags incorrect insight data (e.g. wrong designation in extracted fields).
    Waits for 'correction_reviewed' signal from OA-Admin / Compliance Officer.
    On approval: applies correction and notifies employee.
    SLA: 7 working days per DPDP Act 2023.
    """

    def __init__(self):
        self._reviewed = False
        self._approved = False

    @workflow.signal(name="correction_reviewed")
    def correction_reviewed(self, payload: dict) -> None:
        self._reviewed = True
        self._approved = payload.get("approved", False)

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        reviewed = await workflow.wait_condition(
            lambda: self._reviewed, timeout=timedelta(days=7),
        )
        if reviewed and self._approved:
            await workflow.execute_activity(
                apply_data_correction, params,
                start_to_close_timeout=timedelta(minutes=15), retry_policy=_RETRY,
            )
        await workflow.execute_activity(
            notify_correction_complete,
            {**params, "approved": self._approved, "reviewed_in_time": reviewed},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )


# ── RetentionWorkflow (Pattern 4 — Continue-As-New, 7-year boundary) ─────────

@workflow.defn(name="RetentionWorkflow")
class RetentionWorkflow:
    """
    Starts when a document or employee record is marked for retention.
    Sleeps until the retention period expires (default: 7 years per DPDP + labour law).
    On expiry (and no LegalHold): schedules secure deletion.
    Continue-As-New at 5-year mark to avoid history limit.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        years_str = await workflow.execute_activity(
            get_config_value,
            {"key": "retention_years_default",
             "tenant_id": params.get("tenant_id"), "default": "7"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        elapsed_years   = params.get("elapsed_years", 0)
        remaining_years = int(years_str) - elapsed_years
        if remaining_years > 5:
            await workflow.sleep(timedelta(days=5 * 365))
            workflow.continue_as_new({**params, "elapsed_years": elapsed_years + 5})
            return
        await workflow.sleep(timedelta(days=remaining_years * 365))
        await workflow.execute_activity(
            schedule_document_deletion, params,
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )


# ── AuditArchivalWorkflow (Pattern 3 — Temporal Schedule) ────────────────────

@workflow.defn(name="AuditArchivalWorkflow")
class AuditArchivalWorkflow:
    """
    Moves audit events older than 90 days from YugabyteDB (hot) to Apache Iceberg
    on S3 (cold). Runs nightly. Keeps hot DB lean; cold store retains 7 years.
    Batch size and cutoff age from platform_config.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        result = await workflow.execute_activity(
            archive_audit_events_batch, params,
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=_RETRY,
        )
        # Log result (rows archived, bytes written) — activity handles the write
        _ = result


# ── LegalHoldWorkflow (Pattern 2 — Signal-Driven) ────────────────────────────

@workflow.defn(name="LegalHoldWorkflow")
class LegalHoldWorkflow:
    """
    Freezes all deletions and retention expirations for a given scope
    (employee_id, tenant_id, or document_id) pending legal proceedings.
    Waits for 'release_hold' signal from Platform Admin / Legal team.
    No SLA timeout — holds can be indefinite.
    """

    def __init__(self):
        self._released = False

    @workflow.signal(name="release_hold")
    def release_hold(self, payload: dict) -> None:
        self._released = True

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            apply_legal_hold, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        # Wait indefinitely for release signal
        await workflow.wait_condition(lambda: self._released)
        await workflow.execute_activity(
            release_legal_hold, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )


# ── StatutoryComplianceWorkflow (Pattern 3 — Temporal Schedule) ──────────────

@activity.defn(name="mark_overdue_obligations")
async def mark_overdue_obligations(params: dict) -> dict:
    from db import get_db_connection
    from services.compliance_service import ComplianceService
    async with get_db_connection() as db:
        svc = ComplianceService(db=db)
        return await svc.mark_overdue_obligations(tenant_id=params["tenant_id"])


@activity.defn(name="notify_overdue_obligations")
async def notify_overdue_obligations(params: dict) -> None:
    from db import get_db_connection
    from kafka.producer import get_kafka_producer
    from services.compliance_service import ComplianceService
    tenant_id = params["tenant_id"]
    count = params.get("count", 0)
    async with get_db_connection() as db:
        svc = ComplianceService(db=db)
        await svc.notify_overdue_obligations(tenant_id=tenant_id, count=count)
    # Publish to prana.notifications so NotifConsumer dispatches CHRO alert
    kafka = await get_kafka_producer()
    await kafka.publish(
        "prana.notifications",
        {
            "event_type": "COMPLIANCE_OVERDUE_ALERT",
            "tenant_id": tenant_id,
            "overdue_count": count,
            "recipient_role": "CHRO",
        },
        key=tenant_id,
    )


@workflow.defn(name="StatutoryComplianceWorkflow")
class StatutoryComplianceWorkflow:
    """
    Runs nightly (via Temporal Schedule) per tenant.
    Marks compliance_obligation rows OVERDUE when deadline < today and status != COMPLETE.
    Notifies CHRO of newly-overdue items.

    Pattern 3 — Temporal Schedule (created at startup by worker.py ensure_schedules()).
    Schedule ID: "statutory-compliance-{tenant_id}"
    Cadence: nightly at 00:30 IST (from platform_config.statutory_compliance_check_hour)
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            mark_overdue_obligations,
            {"tenant_id": params["tenant_id"]},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        if result.get("marked_count", 0) > 0:
            await workflow.execute_activity(
                notify_overdue_obligations,
                {"tenant_id": params["tenant_id"], "count": result["marked_count"]},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )
        return result
