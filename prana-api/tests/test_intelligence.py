"""Tests for workflows/intelligence.py and AnomalyDetectionWorkflow."""
import inspect

from workflows.intelligence import CareerInsightWorkflow
from workflows.security import AnomalyDetectionWorkflow


def test_career_insight_workflow_is_thin_shell():
    src = inspect.getsource(CareerInsightWorkflow.run)
    assert "execute_activity" in src, \
        "CareerInsightWorkflow.run must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"


def test_anomaly_detection_uses_continue_as_new_before_history_limit():
    src = inspect.getsource(AnomalyDetectionWorkflow.run)
    assert "continue_as_new" in src, \
        "AnomalyDetectionWorkflow must use continue_as_new to keep history bounded"
    from workflows.security import RENEW_THRESHOLD
    assert RENEW_THRESHOLD > 0, "RENEW_THRESHOLD must be a positive integer"
    assert "RENEW_THRESHOLD" in src, \
        "AnomalyDetectionWorkflow must check RENEW_THRESHOLD before continuing as new"
