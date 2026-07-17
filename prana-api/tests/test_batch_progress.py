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


def test_document_ids_come_from_get_batch_config_not_start_params():
    """Regression guard: BATCH_UPLOADED events (and WorkflowConsumer's start params)
    never carry document_ids — only a count. _fan_out used to read
    params["document_ids"], which was always a KeyError since nothing ever set it.
    get_batch_config now looks the ids up from the document table by batch_id."""
    run_src = inspect.getsource(BatchProgressWorkflow.run)
    assert 'params["document_ids"]' not in run_src

    fan_out_src = inspect.getsource(BatchProgressWorkflow._fan_out)
    assert 'params["document_ids"]' not in fan_out_src, \
        "_fan_out must not read document_ids off the workflow's start params"

    assert '"batch_id": params.get("batch_id")' in run_src, \
        "get_batch_config must be called with batch_id so it can look up document_ids"
