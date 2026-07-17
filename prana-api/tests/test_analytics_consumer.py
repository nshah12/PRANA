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

    consumer._temporal.start_workflow.assert_awaited_once()
    call = consumer._temporal.start_workflow.call_args
    assert call.kwargs["task_queue"] == "insight-queue"
    assert call.kwargs["id"] == "insight-doc-1"


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
