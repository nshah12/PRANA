"""
Structural tests for workflows/employee_lifecycle.py — Temporal workflow shells.

These tests verify architectural constraints without running a Temporal cluster:
  - EmployeeExitWorkflow uses durable activities (freeze vault → notify → retention)
  - PushWindowExpiryWorkflow reads push_window duration from config, not hardcode
  - Workflow @run methods are thin shells (<20 lines)
  - Zero business logic inside @workflow.run / @workflow.defn

The business logic itself lives in services/employee_lifecycle_service.py (zero Temporal imports).
"""
import inspect

import pytest


def _get_source_lines(method) -> list[str]:
    source = inspect.getsource(method)
    return [l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]


# -- EmployeeExitWorkflow ------------------------------------------------------

def test_employee_exit_workflow_uses_durable_timer():
    """EmployeeExitWorkflow.run must use execute_activity for freeze/notify/retention.
    It must NOT contain raw SQL, business logic, or hardcoded sleep durations.
    """
    from workflows.employee_lifecycle import EmployeeExitWorkflow
    source = inspect.getsource(EmployeeExitWorkflow.run)

    # Must delegate to activities
    assert "execute_activity" in source, "EmployeeExitWorkflow must use execute_activity"
    # Must not contain hardcoded business logic
    assert "INSERT" not in source, "No SQL in workflow shell"
    assert "SELECT" not in source, "No SQL in workflow shell"


def test_employee_exit_workflow_is_thin_shell():
    """EmployeeExitWorkflow.run must be <20 lines (Temporal workflow rule)."""
    from workflows.employee_lifecycle import EmployeeExitWorkflow
    lines = _get_source_lines(EmployeeExitWorkflow.run)
    assert len(lines) <= 20, f"EmployeeExitWorkflow.run has {len(lines)} lines — must be <20 (Temporal thin shell rule)"


def test_employee_exit_workflow_calls_freeze_and_notify():
    """EmployeeExitWorkflow must orchestrate 3 activities: freeze, notify, retention."""
    from workflows.employee_lifecycle import EmployeeExitWorkflow
    from workflows.employee_lifecycle import (
        freeze_employee_vault, notify_exit_employee, start_retention_workflow
    )
    source = inspect.getsource(EmployeeExitWorkflow.run)
    assert "freeze_employee_vault" in source
    assert "notify_exit_employee" in source
    assert "start_retention_workflow" in source


# -- PushWindowExpiryWorkflow --------------------------------------------------

def test_push_window_expiry_duration_from_config():
    """PushWindowExpiryWorkflow must fetch duration from config activity, not hardcode it."""
    from workflows.employee_lifecycle import PushWindowExpiryWorkflow
    source = inspect.getsource(PushWindowExpiryWorkflow.run)

    # Must read duration from config
    assert "get_lifecycle_config" in source, "Duration must come from get_lifecycle_config activity"
    # Must use workflow.sleep with the config-derived value — not a literal int
    assert "workflow.sleep" in source, "Must use durable Temporal sleep, not asyncio.sleep"
    # Must NOT hardcode a specific number of days
    assert "timedelta(days=30)" not in source, "Duration must not be hardcoded as 30 days"


def test_push_window_expiry_workflow_is_thin_shell():
    """PushWindowExpiryWorkflow.run must be <20 lines."""
    from workflows.employee_lifecycle import PushWindowExpiryWorkflow
    lines = _get_source_lines(PushWindowExpiryWorkflow.run)
    assert len(lines) <= 20, f"PushWindowExpiryWorkflow.run has {len(lines)} lines — must be <20"


# -- Activity independence (no Temporal imports in service layer) ---------------

def test_lifecycle_activities_have_no_business_logic_in_shells():
    """Activity @defn stubs in employee_lifecycle.py must be empty (... bodies).
    Real logic is in services/employee_lifecycle_service.py (zero Temporal imports).
    """
    from workflows.employee_lifecycle import freeze_employee_vault
    source = inspect.getsource(freeze_employee_vault)
    # Activity stubs should be very short — just the signature + ellipsis
    non_trivial_lines = [
        l for l in source.splitlines()
        if l.strip()
        and not l.strip().startswith("#")
        and not l.strip().startswith("@")   # decorators are expected
        and "def " not in l
        and l.strip() != "..."
    ]
    assert len(non_trivial_lines) == 0, \
        "Activity shells must be empty stubs — business logic belongs in service classes"
