"""Tests for workflows/error_threshold.py — ErrorThresholdEvaluationWorkflow."""
import inspect

from workflows.error_threshold import ErrorThresholdEvaluationWorkflow, ensure_error_threshold_schedule


def test_error_threshold_workflow_is_thin_shell():
    src = inspect.getsource(ErrorThresholdEvaluationWorkflow.run)
    assert "execute_activity" in src or "evaluate_error_thresholds" in src
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper()
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"ErrorThresholdEvaluationWorkflow.run has {len(non_comment)} lines — must be <20"


def test_ensure_schedule_is_idempotent_create_or_update():
    src = inspect.getsource(ensure_error_threshold_schedule)
    assert "get_schedule_handle" in src
    assert "create_schedule" in src
    assert "task_queue=\"secops-queue\"" in src
