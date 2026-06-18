"""Tests for workflows/security.py — security lifecycle workflows."""
import inspect

from workflows.security import (
    PolicyLockWorkflow,
    KMSKeyRotationWorkflow,
    TOTPLockoutWorkflow,
    RENEW_THRESHOLD,
)


def test_policy_lock_workflow_is_signal_driven_interruptible_timer():
    src = inspect.getsource(PolicyLockWorkflow)
    # Must wait for 'unlock_early' signal or timer expiry
    assert "unlock_early" in src, \
        "PolicyLockWorkflow must listen for unlock_early signal"
    assert "workflow.sleep" in src or "wait_condition" in src, \
        "PolicyLockWorkflow must use durable timer (workflow.sleep or workflow.wait_condition)"
    # Duration from config
    assert "policy_lock_default_hours" in src, \
        "Lock duration must come from config, not be hardcoded"


def test_kms_key_rotation_uses_continue_as_new():
    src = inspect.getsource(KMSKeyRotationWorkflow.run)
    assert "continue_as_new" in src, \
        "KMSKeyRotationWorkflow must use continue_as_new to prevent history bloat"
    assert RENEW_THRESHOLD > 0
    assert "RENEW_THRESHOLD" in src, \
        "Must check RENEW_THRESHOLD before calling continue_as_new"


def test_totp_lockout_duration_from_config():
    src = inspect.getsource(TOTPLockoutWorkflow.run)
    assert "totp_lockout_cooldown_minutes" in src, \
        "TOTP lockout duration must be read from config, not hardcoded"
    assert "execute_activity" in src, \
        "TOTPLockoutWorkflow must delegate via execute_activity"
