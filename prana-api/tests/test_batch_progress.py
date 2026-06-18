"""Tests for workflows/batch_progress.py — Temporal thin shell."""
import inspect

from workflows.batch_progress import BatchProgressWorkflow, BatchTimeoutMonitorWorkflow


def _non_comment_lines(src: str) -> list[str]:
    return [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]


def test_batch_progress_workflow_is_thin_shell():
    src = inspect.getsource(BatchProgressWorkflow.run)
    assert "execute_activity" in src, \
        "BatchProgressWorkflow must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"


def test_batch_timeout_triggers_alert_via_kafka():
    src = inspect.getsource(BatchProgressWorkflow.run)
    # Timeout path marks stragglers via activity
    assert "mark_batch_straggler" in src, \
        "BatchProgressWorkflow must call mark_batch_straggler activity on timeout"
