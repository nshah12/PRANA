"""Tests for kafka/consumers/analytics_consumer.py — AnalyticsConsumer."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def consumer():
    from kafka.consumers.analytics_consumer import AnalyticsConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    temporal = AsyncMock()
    redis = AsyncMock()
    return AnalyticsConsumer(settings, temporal_client=temporal, redis=redis)


@pytest.mark.asyncio
async def test_doc_routed_starts_insight_refresh_workflow_from_the_right_module(consumer):
    """Regression guard: this used to do `from workflows.document_pipeline
    import InsightRefreshWorkflow` — that workflow is actually defined in
    workflows/insight_refresh.py, not document_pipeline.py. ImportError the
    instant DOC_ROUTED fired for a resolved employee; no test previously
    exercised this path."""
    event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)

    calls = consumer._temporal.start_workflow.call_args_list
    call = next(c for c in calls if c.kwargs["id"] == "insight-doc-1")
    assert call.kwargs["task_queue"] == "insight-queue"


@pytest.mark.asyncio
async def test_doc_routed_invalidates_vault_completeness_cache(consumer):
    event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)
    consumer._redis.delete.assert_awaited_once_with("vault:t-1")


@pytest.mark.asyncio
async def test_doc_routed_skips_insight_refresh_without_resolved_employee(consumer):
    event = {"tenant_id": "t-1", "employee_uuid": None, "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_doc_routed_starts_market_comp_workflow(consumer):
    """MarketCompWorkflow (workflows/intelligence.py) was fully implemented
    but never started by anything — 2026-08-06 fix. Per-employee workflow ID
    (not per-document) so a burst of uploads for one employee collapses to
    the latest recompute rather than queuing N runs."""
    event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)

    calls = consumer._temporal.start_workflow.call_args_list
    market_comp_call = next(c for c in calls if c.kwargs["id"] == "market-comp-emp-1")
    assert market_comp_call.kwargs["task_queue"] == "insight-queue"


@pytest.mark.asyncio
async def test_doc_routed_skips_market_comp_without_resolved_employee(consumer):
    event = {"tenant_id": "t-1", "employee_uuid": None, "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_doc_routed_starts_career_insight_workflow(consumer):
    """CareerInsightWorkflow (workflows/intelligence.py) — build_career_insight
    raised NotImplementedError until 2026-08-07 (no prana-ai endpoint existed);
    now that it does, wire the same DOC_ROUTED trigger convention as
    InsightRefreshWorkflow/MarketCompWorkflow. Per-employee workflow ID."""
    event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)

    calls = consumer._temporal.start_workflow.call_args_list
    career_call = next(c for c in calls if c.kwargs["id"] == "career-insight-emp-1")
    assert career_call.kwargs["task_queue"] == "insight-queue"


@pytest.mark.asyncio
async def test_doc_routed_skips_career_insight_without_resolved_employee(consumer):
    event = {"tenant_id": "t-1", "employee_uuid": None, "document_id": "doc-1"}
    await consumer._handle_doc_routed(event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_doc_routed_starts_skill_gap_workflow_for_career_letter_doc_types(consumer):
    """SkillGapWorkflow — unlike InsightRefreshWorkflow/MarketCompWorkflow/
    CareerInsightWorkflow (which fire on every DOC_ROUTED), this one is gated
    to only fire when the routed doc is itself a career-letter type — feeding
    it a SALARY_SLIP/FORM_16 doc_type would be pointless since career_event
    never gets a row for those (pipeline/stage06_route.py's _doc_type_to_event
    maps them to None). Per-employee workflow ID, same collapsing rationale."""
    for doc_type in ("OFFER_LETTER", "APPOINTMENT_LETTER", "PROMOTION_LETTER",
                      "INCREMENT_LETTER", "JOINING_LETTER"):
        consumer._temporal.start_workflow.reset_mock()
        event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1", "doc_type": doc_type}
        await consumer._handle_doc_routed(event)

        calls = consumer._temporal.start_workflow.call_args_list
        skill_gap_call = next((c for c in calls if c.kwargs["id"] == "skill-gap-emp-1"), None)
        assert skill_gap_call is not None, f"SkillGapWorkflow must start for doc_type={doc_type}"
        assert skill_gap_call.kwargs["task_queue"] == "insight-queue"


@pytest.mark.asyncio
async def test_doc_routed_skips_skill_gap_for_non_career_letter_doc_types(consumer):
    for doc_type in ("SALARY_SLIP", "FORM_16", "PF_ACKNOWLEDGEMENT"):
        consumer._temporal.start_workflow.reset_mock()
        event = {"tenant_id": "t-1", "employee_uuid": "emp-1", "document_id": "doc-1", "doc_type": doc_type}
        await consumer._handle_doc_routed(event)

        calls = consumer._temporal.start_workflow.call_args_list
        skill_gap_call = next((c for c in calls if c.kwargs["id"] == "skill-gap-emp-1"), None)
        assert skill_gap_call is None, f"SkillGapWorkflow must NOT start for doc_type={doc_type}"


@pytest.mark.asyncio
async def test_doc_routed_skips_skill_gap_without_resolved_employee(consumer):
    event = {"tenant_id": "t-1", "employee_uuid": None, "document_id": "doc-1", "doc_type": "OFFER_LETTER"}
    await consumer._handle_doc_routed(event)
    consumer._temporal.start_workflow.assert_not_awaited()
