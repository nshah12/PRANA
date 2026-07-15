"""Tests for workflows/audit_integrity.py — AuditIntegrityVerificationWorkflow."""
import inspect

from workflows.audit_integrity import AuditIntegrityVerificationWorkflow, ensure_audit_integrity_schedule


def test_audit_integrity_workflow_is_thin_shell():
    src = inspect.getsource(AuditIntegrityVerificationWorkflow.run)
    assert "execute_activity" in src or "verify_audit_integrity" in src, \
        "AuditIntegrityVerificationWorkflow must delegate to execute_activity"
    assert "SELECT" not in src.upper() and "INSERT" not in src.upper(), \
        "No SQL in workflow shell"
    non_comment = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert len(non_comment) <= 20, \
        f"AuditIntegrityVerificationWorkflow.run has {len(non_comment)} lines — must be <20"


def test_ensure_schedule_is_idempotent_create_or_update():
    src = inspect.getsource(ensure_audit_integrity_schedule)
    assert "get_schedule_handle" in src
    assert "create_schedule" in src
    assert "task_queue=\"secops-queue\"" in src, \
        "AuditIntegrityVerificationWorkflow must run on secops-queue (see workflows/CLAUDE.md)"
