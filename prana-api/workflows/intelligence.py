"""
Intelligence layer workflows — thin Temporal shells.
Business logic lives in prana-ai/ (GPU worker) and services/analytics_service.py.

Task queues: insight-queue, analytics-queue

Workflows (7 — InsightRefreshWorkflow is in insight_refresh.py):
  CareerInsightWorkflow         — build/refresh career timeline for an employee
  VaultCompletenessWorkflow     — per-employee vault health scoring
  AnomalyAcknowledgementWorkflow — CFO acknowledges a financial anomaly
  DigestWorkflow                — weekly / monthly summary email (Temporal Schedule)
  PeerBenchmarkWorkflow         — cross-tenant peer salary benchmark (no PII)
  SkillGapWorkflow              — skill gap analysis from designation progression
  MarketCompWorkflow            — market compensation comparison (external data)
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


# ── Activities (stubs — implementations in services/analytics_service.py + prana-ai) ──

@activity.defn(name="build_career_insight")
async def build_career_insight(params: dict) -> dict: ...

@activity.defn(name="write_career_insight")
async def write_career_insight(params: dict) -> None: ...

@activity.defn(name="score_vault_completeness")
async def score_vault_completeness(params: dict) -> dict: ...

@activity.defn(name="write_vault_completeness")
async def write_vault_completeness(params: dict) -> None: ...

@activity.defn(name="record_anomaly_ack")
async def record_anomaly_ack(params: dict) -> None: ...

@activity.defn(name="build_weekly_digest")
async def build_weekly_digest(params: dict) -> dict:
    """
    Builds digest data for all configured roles for the tenant.
    Full implementation lives in the analytics-queue worker which injects a DB pool.
    DigestService.build_*_digest() is called per role; results are merged into params
    and forwarded to send_digest_email.
    """
    return {"digest_type": "weekly", "tenant_id": params.get("tenant_id"), "data": {}}


@activity.defn(name="build_monthly_digest")
async def build_monthly_digest(params: dict) -> dict:
    return {"digest_type": "monthly", "tenant_id": params.get("tenant_id"), "data": {}}


@activity.defn(name="send_digest_email")
async def send_digest_email(params: dict) -> None:
    """
    Publishes digest payload to prana.notifications Kafka topic.
    NotifConsumer dispatches via AWS SES — never calls SES directly from here.
    """
    ...

@activity.defn(name="build_peer_benchmark")
async def build_peer_benchmark(params: dict) -> dict: ...

@activity.defn(name="write_peer_benchmark")
async def write_peer_benchmark(params: dict) -> None: ...

@activity.defn(name="build_skill_gap_analysis")
async def build_skill_gap_analysis(params: dict) -> dict: ...

@activity.defn(name="write_skill_gap")
async def write_skill_gap(params: dict) -> None: ...

@activity.defn(name="build_market_comp")
async def build_market_comp(params: dict) -> dict: ...

@activity.defn(name="write_market_comp")
async def write_market_comp(params: dict) -> None: ...


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


# ── VaultCompletenessWorkflow (Pattern 1 — fast) ─────────────────────────────

@workflow.defn(name="VaultCompletenessWorkflow")
class VaultCompletenessWorkflow:
    """
    Scores an individual employee's vault completeness across all required doc types.
    Writes result to employee_master.vault_completeness (0–100 integer).
    Triggered by VaultHealthWorkflow and after self-upload.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            score_vault_completeness, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_vault_completeness, {**params, **result},
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
