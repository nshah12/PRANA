"""Tests for workflows/document_pipeline.py — 6-stage pipeline workflow."""
import inspect

from workflows.document_pipeline import DocumentPipelineWorkflow


def test_pipeline_workflow_is_thin_shell_no_db_calls_in_run():
    src = inspect.getsource(DocumentPipelineWorkflow.run)
    assert "SELECT" not in src.upper(), "No SQL SELECT in workflow shell"
    assert "INSERT" not in src.upper(), "No SQL INSERT in workflow shell"
    assert "execute_activity" in src, "Must delegate all work to execute_activity"


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
    # When stage05 returns needs_exception=True, raise_exception activity is called
    assert "needs_exception" in src, "Pipeline must check needs_exception from stage05"
    assert "stage06_raise_exception" in src, \
        "Pipeline must call stage06_raise_exception when confidence is below threshold"
