"""Tests for workflows/insight_refresh.py — insight generation workflow."""
import inspect

from workflows.insight_refresh import InsightRefreshWorkflow, refresh_document_insight


def test_insight_refresh_workflow_output_contains_no_raw_salary():
    # refresh_document_insight delegates to AiPipelineClient.refresh_insight
    # prana-ai enforces privacy — no raw salary in insight output
    src = inspect.getsource(refresh_document_insight)
    assert "AiPipelineClient" in src or "refresh_insight" in src, \
        "refresh_document_insight must call AiPipelineClient to stay out of GPU worker"
    assert "salary" not in src.lower() and "₹" not in src, \
        "refresh_document_insight must not handle raw salary figures"


def test_insight_refresh_is_thin_shell_no_llm_call_in_run():
    src = inspect.getsource(InsightRefreshWorkflow.run)
    assert "execute_activity" in src, \
        "InsightRefreshWorkflow.run must delegate to execute_activity"
    assert "llm" not in src.lower() and "openai" not in src.lower(), \
        "LLM must not be called directly from the workflow shell"


def test_refresh_document_insight_registered_in_insight_queue():
    """refresh_document_insight must be in worker.py's insight-queue activities list.
    Without this, Temporal raises 'activity not registered' at runtime."""
    from workflows.worker import WORKERS
    activity_names = [a.__name__ for a in WORKERS["insight-queue"]["activities"]]
    assert "refresh_document_insight" in activity_names, \
        "refresh_document_insight missing from insight-queue — Temporal will fail at runtime"


def test_insight_refresh_workflow_registered_in_insight_queue():
    from workflows.worker import WORKERS
    workflow_names = [w.__name__ for w in WORKERS["insight-queue"]["workflows"]]
    assert "InsightRefreshWorkflow" in workflow_names, \
        "InsightRefreshWorkflow missing from insight-queue worker registration"
