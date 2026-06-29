"""Tests for workflows/activities.py — Temporal activity implementations."""
import inspect
import pathlib


def test_activities_contain_no_temporal_imports():
    # activities.py imports `from temporalio import activity` (decorator only — allowed)
    # Business logic service classes (encryption_service, compliance_service, etc.)
    # must NOT import temporalio — they are pure Python.
    #
    # EXCEPTION: ai_client.py is an infrastructure adapter, not business logic.
    # It raises ApplicationError so Temporal activities can propagate retryable/non-retryable
    # pipeline errors correctly (analogous to encryption_service importing boto3).
    _ALLOWED_TEMPORAL_IMPORTS = {"ai_client.py"}
    services_dir = pathlib.Path(__file__).parent.parent / "services"
    for src_file in services_dir.glob("*.py"):
        if src_file.name in _ALLOWED_TEMPORAL_IMPORTS:
            continue
        src = src_file.read_text(encoding="utf-8")
        assert "from temporalio" not in src and "import temporalio" not in src, \
            f"{src_file.name} must not import temporalio — business logic is pure Python"


def test_activity_callable_without_temporal_cluster():
    # Activities in activities.py are regular async functions decorated with @activity.defn
    # They can be imported and called without a Temporal cluster running
    from workflows import activities
    import asyncio

    # stage05_resolve is a real async function callable without cluster
    assert callable(activities.stage05_resolve)
    assert callable(activities.get_config_value)
    assert callable(activities.execute_erasure)
