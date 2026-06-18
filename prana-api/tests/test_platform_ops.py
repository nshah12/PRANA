"""
Structural tests for workflows/platform_ops.py — Platform Operations workflows.

Covers:
  - PlatformSummaryWorkflow is a thin Temporal shell (Pattern 3 — Schedule)
    that reads interval from config, not hardcoded
  - ClamAVUpdateWorkflow uses Temporal schedule (Pattern 3) — no raw cron
"""
import inspect

import pytest


def _get_source(cls_or_fn) -> str:
    return inspect.getsource(cls_or_fn)


# -- PlatformSummaryWorkflow -----------------------------------------------

def test_platform_summary_schedule_interval_from_config():
    """PlatformSummaryWorkflow must delegate to activities, not hardcode logic.
    The schedule interval is configured via 'platform_summary_interval_minutes' at
    schedule creation time (see workflows/CLAUDE.md Pattern 3) — never hardcoded.
    Verify the workflow class uses execute_activity and no raw sleep/polling.
    """
    from workflows.platform_ops import PlatformSummaryWorkflow

    source = _get_source(PlatformSummaryWorkflow.run)

    # Must use execute_activity — no business logic inline
    assert "execute_activity" in source, \
        "PlatformSummaryWorkflow must delegate to execute_activity"

    # Must call both metrics collection and write activities
    assert "collect_platform_metrics" in source, \
        "Must collect metrics via activity"
    assert "write_platform_summary" in source, \
        "Must write summary via activity"

    # Must not hardcode any duration
    assert "timedelta(days=" not in source, \
        "Duration must not be hardcoded in workflow shell"

    # No raw SQL
    assert "SELECT" not in source and "INSERT" not in source, \
        "No SQL in workflow shell"


def test_platform_summary_workflow_is_thin_shell():
    """PlatformSummaryWorkflow.run must be <20 lines (Temporal thin shell rule)."""
    from workflows.platform_ops import PlatformSummaryWorkflow

    lines = [
        l for l in _get_source(PlatformSummaryWorkflow.run).splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert len(lines) <= 20, \
        f"PlatformSummaryWorkflow.run has {len(lines)} lines — must be <20"


# -- ClamAVUpdateWorkflow --------------------------------------------------

def test_clamav_update_workflow_uses_temporal_schedule():
    """ClamAVUpdateWorkflow must use execute_activity for signature pull.
    It runs on a Temporal Schedule (Pattern 3) — not a cron job or raw sleep loop.
    """
    from workflows.platform_ops import ClamAVUpdateWorkflow

    source = _get_source(ClamAVUpdateWorkflow.run)

    # Must delegate to an activity — no direct subprocess/shell calls
    assert "execute_activity" in source, \
        "ClamAVUpdateWorkflow must delegate to execute_activity"
    assert "pull_clamav_signatures" in source, \
        "Must call pull_clamav_signatures activity"

    # No raw OS calls or sleep
    assert "subprocess" not in source, "No subprocess in workflow shell"
    assert "asyncio.sleep" not in source, "Use workflow.sleep (durable), not asyncio.sleep"


def test_clamav_update_workflow_is_thin_shell():
    """ClamAVUpdateWorkflow.run must be <20 lines."""
    from workflows.platform_ops import ClamAVUpdateWorkflow

    lines = [
        l for l in _get_source(ClamAVUpdateWorkflow.run).splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert len(lines) <= 20, \
        f"ClamAVUpdateWorkflow.run has {len(lines)} lines — must be <20"
