"""Tests for workflows/system_health.py — system health monitoring workflow."""
import inspect

from workflows.system_health import SystemHealthWorkflow


def test_system_health_workflow_is_thin_shell():
    src = inspect.getsource(SystemHealthWorkflow.run)
    assert "execute_activity" in src or "run_health_checks" in src, \
        "SystemHealthWorkflow must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"SystemHealthWorkflow.run has {len(non_comment)} lines — must be <20"
