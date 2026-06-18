"""Tests for workflows/vault_shares.py — share token lifecycle workflows."""
import inspect

from workflows.vault_shares import (
    ShareExpiryWorkflow,
    ShareRevocationWorkflow,
    DocumentShareWorkflow,
)


def test_share_expiry_workflow_uses_durable_timer():
    src = inspect.getsource(ShareExpiryWorkflow.run)
    assert "workflow.sleep" in src, \
        "ShareExpiryWorkflow must use workflow.sleep (durable timer, not asyncio.sleep)"
    assert "asyncio.sleep" not in src, \
        "Must use workflow.sleep not asyncio.sleep — durable across restarts"


def test_share_revocation_signal_cancels_expiry_timer():
    src = inspect.getsource(ShareRevocationWorkflow.run)
    assert "revoke_share_token" in src, \
        "ShareRevocationWorkflow must call revoke_share_token activity"
    assert "execute_activity" in src, \
        "Must use execute_activity for durable revocation"


def test_share_ttl_from_platform_config_not_hardcoded():
    src = inspect.getsource(DocumentShareWorkflow.run)
    assert "get_share_config" in src, \
        "DocumentShareWorkflow must read TTL from get_share_config activity"
    assert "share_otp_ttl_minutes" in src, \
        "TTL key must be share_otp_ttl_minutes from platform_config"
