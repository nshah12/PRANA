"""Tests for workflows/document_pipeline.py — 6-stage pipeline workflow."""
import inspect

from workflows.document_pipeline import DocumentPipelineWorkflow


def test_stage_activities_are_the_same_objects_as_workflows_activities():
    """Regression guard: document_pipeline.py used to redeclare stage02-06 (and
    update_pipeline_status) as its own bare-stub @activity.defn functions,
    shadowing the real implementations in workflows/activities.py by name only
    — the exact ACTIVITY-01 hazard (a real compliance.py instance of this
    shipped and went unnoticed for a while). Now this file imports the real
    functions directly, so there is exactly one declaration per activity name
    and no way for worker.py's registration to accidentally pick the wrong one."""
    import workflows.activities as real
    import workflows.document_pipeline as pipeline

    for name in (
        "stage02_encrypt", "stage03_scan", "stage04_extract",
        "stage04_write_unclassified", "stage05_resolve",
        "stage05_handle_cross_tenant_violation", "stage06_route",
        "stage06_raise_exception", "update_pipeline_status",
    ):
        assert getattr(pipeline, name) is getattr(real, name), \
            f"workflows.document_pipeline.{name} must be the same object as workflows.activities.{name}"


def test_embedding_activities_intentionally_have_no_prana_api_implementation():
    """compute_document_embedding/write_document_embedding are registered by
    prana-ai's own worker on the shared resolution-queue (worker.py's
    "resolution-queue" entry has activities=[] with that exact comment) —
    prana-api must never define a real body for these, or the two processes
    would race to register the same activity name."""
    # Neither name should appear in workflows/activities.py — this file is the
    # only place they're declared, and deliberately left unimplemented.
    import workflows.activities as real
    assert not hasattr(real, "compute_document_embedding")
    assert not hasattr(real, "write_document_embedding")


def test_pipeline_workflow_is_thin_shell_no_db_calls_in_run():
    src = inspect.getsource(DocumentPipelineWorkflow.run)
    assert "SELECT" not in src.upper(), "No SQL SELECT in workflow shell"
    assert "INSERT" not in src.upper(), "No SQL INSERT in workflow shell"
    assert "execute_activity" in src, "Must delegate all work to execute_activity"


def test_stage06_routed_starts_vault_health_child_workflow():
    """Regression: VaultHealthWorkflow's own docstring claims "Triggered by
    DocumentPipelineWorkflow stage 06", but nothing anywhere ever started it —
    stage06_route just ran the activity and returned. employee_master.
    vault_completeness was never recomputed after a document actually routed."""
    run_src = inspect.getsource(DocumentPipelineWorkflow.run)
    assert "stage06_route" in run_src
    assert "_finish_routed" in run_src, \
        "run() must delegate post-routing work (starting VaultHealthWorkflow) to a helper"

    finish_src = inspect.getsource(DocumentPipelineWorkflow._finish_routed)
    assert "VaultHealthWorkflow" in finish_src, \
        "DocumentPipelineWorkflow must start VaultHealthWorkflow after stage06_route"
    assert "execute_child_workflow" in finish_src


def test_pipeline_6_stages_executed_in_order():
    src = inspect.getsource(DocumentPipelineWorkflow.run)
    # All 6 stage activities must appear
    assert "stage02_encrypt" in src
    assert "stage03_scan" in src
    assert "stage04_extract" in src
    assert "stage05_resolve" in src
    assert "stage06_route" in src
    # Order: stage02 before stage03 before stage04 before stage05 before stage06
    assert src.index("stage02_encrypt") < src.index("stage03_scan"), "stage02 before stage03"
    assert src.index("stage03_scan")   < src.index("stage04_extract"), "stage03 before stage04"
    assert src.index("stage04_extract") < src.index("stage05_resolve"), "stage04 before stage05"
    assert src.index("stage05_resolve") < src.index("stage06_route"), "stage05 before stage06"


def test_pipeline_exception_confidence_below_threshold_raises_exception():
    src = inspect.getsource(DocumentPipelineWorkflow.run)
    # When stage05 returns needs_exception=True, exception wait helper is called
    assert "needs_exception" in src, "Pipeline must check needs_exception from stage05"
    assert "_handle_exception_wait" in src, \
        "Pipeline must delegate to _handle_exception_wait when confidence is below threshold"
    # stage06_raise_exception must be called somewhere in the workflow class
    workflow_src = inspect.getsource(DocumentPipelineWorkflow)
    assert "stage06_raise_exception" in workflow_src, \
        "stage06_raise_exception must be called within DocumentPipelineWorkflow"
