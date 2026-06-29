"""
Structural tests for workflows/tenant.py — Tenant lifecycle Temporal workflows.

Covers:
  - TenantProvisioningWorkflow is a thin shell calling 'provision_tenant' activity
  - DomainVerificationWorkflow reads poll interval + max hours from config activity
    (never hardcoded); uses elapsed loop, not asyncio.sleep
"""
import inspect

import pytest


def _get_source(cls_or_fn) -> str:
    return inspect.getsource(cls_or_fn)


# -- TenantProvisioningWorkflow -------------------------------------------

def test_tenant_provisioning_workflow_creates_kek():
    """TenantProvisioningWorkflow.run must call 'provision_tenant' activity.
    KEK creation is part of the provision_tenant activity (KMS call happens there).
    The workflow shell must NOT contain any KMS client calls directly.
    """
    from workflows.tenant import TenantProvisioningWorkflow

    source = _get_source(TenantProvisioningWorkflow.run)

    # Must delegate to execute_activity — no KMS calls in the workflow shell
    assert "execute_activity" in source, \
        "TenantProvisioningWorkflow must use execute_activity"
    assert "provision_tenant" in source, \
        "TenantProvisioningWorkflow must call provision_tenant activity"

    # No KMS client calls directly in the workflow shell
    assert "kms" not in source.lower(), \
        "KMS calls must live in service layer, not workflow shell"

    # No SQL
    assert "INSERT" not in source and "UPDATE" not in source, \
        "No SQL in workflow shell"


def test_tenant_provisioning_workflow_is_thin_shell():
    """TenantProvisioningWorkflow.run must be <20 lines."""
    from workflows.tenant import TenantProvisioningWorkflow

    lines = [
        l for l in _get_source(TenantProvisioningWorkflow.run).splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert len(lines) <= 20, \
        f"TenantProvisioningWorkflow.run has {len(lines)} lines — must be <20"


# -- DomainVerificationWorkflow -------------------------------------------

def test_domain_verification_polls_until_48h_max_from_config():
    """DomainVerificationWorkflow must read max_hours from config activity.
    It must NOT hardcode 48 hours anywhere in the workflow run method.
    The workflow polls until verified or max_seconds elapsed (from config).
    """
    from workflows.tenant import DomainVerificationWorkflow

    source = _get_source(DomainVerificationWorkflow.run)

    # Must read config from activity — never hardcoded constants
    assert "get_tenant_onboarding_config" in source, \
        "Must read domain_verification_max_hours from config activity"
    assert "domain_verification_poll_minutes" in source, \
        "Poll interval must come from config"
    assert "domain_verification_max_hours" in source, \
        "Max hours must come from config"

    # Must NOT hardcode 48 hours
    assert "48" not in source or "max_hours" in source, \
        "If 48 appears, it must be from config, not a literal"
    assert "timedelta(hours=48)" not in source, \
        "48h must not be hardcoded as a timedelta literal"

    # Must check DNS TXT record via activity
    assert "check_dns_txt_record" in source, \
        "DNS polling must go through check_dns_txt_record activity"


def test_domain_verification_marks_failed_on_timeout():
    """DomainVerificationWorkflow must call mark_tenant_verification_failed on timeout."""
    from workflows.tenant import DomainVerificationWorkflow

    # run() delegates outcome handling to _finalize() — check the class source
    workflow_src = inspect.getsource(DomainVerificationWorkflow)

    assert "mark_tenant_verification_failed" in workflow_src, \
        "Timeout path must mark tenant as VERIFICATION_FAILED via activity"
    assert "VERIFICATION_FAILED" in workflow_src, \
        "Expected outcome constant 'VERIFICATION_FAILED' in workflow"
