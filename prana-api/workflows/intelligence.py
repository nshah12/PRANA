"""
Intelligence layer workflows — thin Temporal shells.
Business logic lives in prana-ai/ (GPU worker) and services/analytics_service.py.

Task queues: insight-queue, analytics-queue

Workflows (6 — InsightRefreshWorkflow is in insight_refresh.py):
  CareerInsightWorkflow         — build/refresh career timeline for an employee
  AnomalyAcknowledgementWorkflow — CFO acknowledges a financial anomaly
  DigestWorkflow                — weekly / monthly summary email (Temporal Schedule)
  PeerBenchmarkWorkflow         — cross-tenant peer salary benchmark (no PII)
  SkillGapWorkflow              — skill gap analysis from designation progression
  MarketCompWorkflow            — market compensation comparison (external data)

VaultCompletenessWorkflow removed 2026-08-06 — was never triggered by
anything (registered on a worker queue but no start_workflow call existed
anywhere), so it was dead code duplicating employee_master.vault_completeness
writes against VaultHealthWorkflow (workflows/employee_lifecycle.py), which
IS live-triggered. Its richer 3-category scoring formula was merged into
VaultHealthWorkflow's activity instead of being thrown away — see
services/employee_lifecycle_service.py's recompute_vault_completeness.
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Activities (implementations in services/analytics_service.py) ───────────

async def _connect():
    import asyncpg

    from config import get_settings

    settings = get_settings()
    return await asyncpg.connect(settings.db_dsn)


@activity.defn(name="build_career_insight")
async def build_career_insight(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_career_insight(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="write_career_insight")
async def write_career_insight(params: dict) -> None:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        await AnalyticsService(db).write_career_insight(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
            insights=params.get("insights", {}),
        )
    finally:
        await db.close()

@activity.defn(name="record_anomaly_ack")
async def record_anomaly_ack(params: dict) -> None:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        await AnalyticsService(db).record_anomaly_ack(
            anomaly_id=params["anomaly_id"], acked=params.get("acked", False),
            note=params.get("note", ""), acknowledged_by=params.get("acknowledged_by"),
        )
    finally:
        await db.close()

@activity.defn(name="build_weekly_digest")
async def build_weekly_digest(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_digest(tenant_id=params["tenant_id"], digest_type="weekly")
    finally:
        await db.close()


@activity.defn(name="build_monthly_digest")
async def build_monthly_digest(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_digest(tenant_id=params["tenant_id"], digest_type="monthly")
    finally:
        await db.close()


@activity.defn(name="send_digest_email")
async def send_digest_email(params: dict) -> None:
    from kafka.producer import get_kafka_producer
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        kafka = await get_kafka_producer()
        await AnalyticsService(db, kafka=kafka).send_digest_email(
            tenant_id=params["tenant_id"], digest_type=params["digest_type"], data=params.get("data", {}),
        )
    finally:
        await db.close()

@activity.defn(name="build_peer_benchmark")
async def build_peer_benchmark(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_peer_benchmark(
            tenant_id=params["tenant_id"], grade=params["grade"], department=params["department"],
        )
    finally:
        await db.close()

@activity.defn(name="write_peer_benchmark")
async def write_peer_benchmark(params: dict) -> None:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        await AnalyticsService(db).write_peer_benchmark(
            tenant_id=params["tenant_id"], band_label=params["band_label"], cache_value=params["cache_value"],
        )
    finally:
        await db.close()

@activity.defn(name="build_skill_gap_analysis")
async def build_skill_gap_analysis(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_skill_gap_analysis(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()

@activity.defn(name="write_skill_gap")
async def write_skill_gap(params: dict) -> None:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        await AnalyticsService(db).write_skill_gap(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
            insights=params.get("insights", {}),
        )
    finally:
        await db.close()

@activity.defn(name="build_market_comp")
async def build_market_comp(params: dict) -> dict:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        return await AnalyticsService(db).build_market_comp(employee_uuid=params["employee_uuid"])
    finally:
        await db.close()

@activity.defn(name="write_market_comp")
async def write_market_comp(params: dict) -> None:
    from services.analytics_service import AnalyticsService

    db = await _connect()
    try:
        await AnalyticsService(db).write_market_comp(
            employee_uuid=params["employee_uuid"], tenant_id=params.get("tenant_id"),
            insights=params.get("insights", {}),
        )
    finally:
        await db.close()


# ── CareerInsightWorkflow (Pattern 1 — fast) ─────────────────────────────────

@workflow.defn(name="CareerInsightWorkflow")
class CareerInsightWorkflow:
    """
    Builds / refreshes the career timeline and progression insights for an employee.
    Triggered after every DocumentPipelineWorkflow ROUTED event via WorkflowConsumer.
    Delegates heavy LLM work to prana-ai via HTTP activity.
    Output: insights JSONB (no raw ₹ figures) written to employee_insight table.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            build_career_insight, params,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_career_insight, {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result



# ── AnomalyAcknowledgementWorkflow (Pattern 5 — Human Signal) ────────────────

@workflow.defn(name="AnomalyAcknowledgementWorkflow")
class AnomalyAcknowledgementWorkflow:
    """
    Raised when CFO analytics flags a financial anomaly (salary spike, ghost employee).
    Waits for CFO to acknowledge via 'acknowledge' signal (POST /cfo/anomalies/{id}/ack).
    SLA: 7 days before escalating to Platform Admin.
    """

    def __init__(self):
        self._acked = False
        self._ack_note: str = ""

    @workflow.signal(name="acknowledge")
    def acknowledge(self, payload: dict) -> None:
        self._acked = True
        self._ack_note = payload.get("note", "")

    @workflow.run
    async def run(self, params: dict) -> None:
        acked = await workflow.wait_condition(
            lambda: self._acked,
            timeout=timedelta(days=7),
        )
        await workflow.execute_activity(
            record_anomaly_ack,
            {**params, "acked": acked and self._acked, "note": self._ack_note},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── DigestWorkflow (Pattern 3 — Temporal Schedule) ───────────────────────────

@workflow.defn(name="DigestWorkflow")
class DigestWorkflow:
    """
    Sends weekly (Mondays 08:00 IST) and monthly (1st, 08:00 IST) digest emails
    to CHROs. Created once at startup as a Temporal Schedule — not triggered per-event.
    Schedule cadence read from platform_config at creation time (updatable without deploy).
    The 'digest_type' param ('weekly' | 'monthly') determines report content.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        build_act = build_monthly_digest if params.get("digest_type") == "monthly" else build_weekly_digest
        timeout   = timedelta(hours=1) if params.get("digest_type") == "monthly" else timedelta(minutes=30)
        result = await workflow.execute_activity(
            build_act, params, start_to_close_timeout=timeout, retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            send_digest_email, {**params, **result},
            start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY,
        )


async def ensure_digest_schedules(client, weekly_cron: str, monthly_cron: str) -> None:
    """Called at prana-api startup to register both Temporal Schedules (idempotent).
    Cadence comes from platform_config.digest_weekly_cron / digest_monthly_cron —
    never hardcoded here."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    for schedule_id, cron, digest_type in (
        ("digest-weekly", weekly_cron, "weekly"),
        ("digest-monthly", monthly_cron, "monthly"),
    ):
        new_spec = ScheduleSpec(cron_expressions=[cron], time_zone_name="Asia/Kolkata")
        try:
            handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
            await handle.describe()
            async def _updater(inp, _spec=new_spec):
                return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=_spec))
            await handle.update(_updater)
        except RPCError:
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        DigestWorkflow.run, {"digest_type": digest_type},
                        id=f"{schedule_id}-run", task_queue="insight-queue",
                    ),
                    spec=new_spec,
                ),
            )


# ── PeerBenchmarkWorkflow (Pattern 1 — fast, cross-tenant, no PII) ───────────

@workflow.defn(name="PeerBenchmarkWorkflow")
class PeerBenchmarkWorkflow:
    """
    Builds a cross-tenant peer comparison (designation + industry + city cohort).
    Output: percentile bands only — no individual salary figures exposed cross-tenant.
    Privacy: aggregated over minimum cohort_size (default: 50) per DPDP k-anonymity.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            build_peer_benchmark, params,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_peer_benchmark, {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result


# ── SkillGapWorkflow (Pattern 1 — fast) ──────────────────────────────────────

@workflow.defn(name="SkillGapWorkflow")
class SkillGapWorkflow:
    """
    Derives skill gap from designation progression in offer/appraisal/promotion letters.
    Output: skill_gap_insights JSONB written to employee_insight table.
    Triggered after every new career letter ROUTED.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            build_skill_gap_analysis, params,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_skill_gap, {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result


# ── MarketCompWorkflow (Pattern 1 — fast) ────────────────────────────────────

@workflow.defn(name="MarketCompWorkflow")
class MarketCompWorkflow:
    """
    Compares employee's growth trajectory against external market compensation data.
    Data source: embedded market comp dataset (no external API call in this version).
    Output: market_comp_insights JSONB — percentile band only, no raw ₹ figures.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            build_market_comp, params,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_market_comp, {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result
