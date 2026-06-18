"""
InsightRefreshWorkflow — thin Temporal shell.
Triggered by DocumentPipelineWorkflow after stage06 ROUTED.

Business logic lives in prana-ai/insights/career_insight_service.py.
This file is the Temporal adapter only.

Task queue: insight-queue
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

TASK_QUEUE = "insight-queue"

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


@activity.defn(name="refresh_document_insight")
async def refresh_document_insight(params: dict) -> None:
    """
    Generate insight text for one ROUTED document and upsert into Qdrant.
    Implemented in prana-ai; called here via HTTP activity.
    """
    from services.ai_client import AiPipelineClient
    await AiPipelineClient().refresh_insight(
        document_id=params["document_id"],
        employee_uuid=params["employee_uuid"],
        doc_type=params["doc_type"],
        doc_period=params.get("doc_period"),
        benchmarks=params.get("benchmarks", {}),
    )


@workflow.defn(name="InsightRefreshWorkflow")
class InsightRefreshWorkflow:
    """
    Generates LLM insight text and embeddings for a single ROUTED document.
    Triggered immediately after DocumentPipelineWorkflow completes with status ROUTED.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            refresh_document_insight,
            params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
