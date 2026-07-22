"""Tests for TenantConsumer — prana.tenant.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def consumer():
    from kafka.consumers.tenant_consumer import TenantConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    temporal = AsyncMock()
    return TenantConsumer(settings, temporal_client=temporal, db_pool=MagicMock())


@pytest.mark.asyncio
async def test_tenant_created_starts_provisioning_workflow(consumer):
    event = {"event_type": "TENANT_CREATED", "tenant_id": "t-1", "domain": "co.com"}
    await consumer._dispatch("TENANT_CREATED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    call = consumer._temporal.start_workflow.call_args
    assert "t-1" in call.kwargs["id"]
    # TenantProvisioningWorkflow is registered on admin-queue in worker.py, not
    # prana-admin — a wrong queue means the workflow starts but is never polled.
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_tenant_offboarded_starts_offboarding_workflow(consumer):
    event = {"event_type": "TENANT_OFFBOARDED", "tenant_id": "t-2"}
    await consumer._dispatch("TENANT_OFFBOARDED", event)
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "TenantOffboardingWorkflow"
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_tenant_activated_starts_no_workflow(consumer):
    """Regression guard: this used to start "TenantOnboardingWorkflow" — never
    @workflow.defn'd anywhere. The provisioning/welcome-email work it would have
    done already happens in TenantProvisioningWorkflow off TENANT_CREATED."""
    event = {"event_type": "TENANT_ACTIVATED", "tenant_id": "t-5"}
    with patch("workflows.compliance.ensure_one_tenant_statutory_schedule", AsyncMock()):
        await consumer._dispatch("TENANT_ACTIVATED", event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_activated_ensures_statutory_compliance_schedule(consumer):
    """Regression: StatutoryComplianceWorkflow's own docstring claims a per-tenant
    schedule gets created — nothing ever triggered it for newly-activated tenants."""
    event = {"event_type": "TENANT_ACTIVATED", "tenant_id": "t-5"}
    with patch("workflows.compliance.ensure_one_tenant_statutory_schedule", AsyncMock()) as mock_ensure:
        await consumer._dispatch("TENANT_ACTIVATED", event)
    mock_ensure.assert_awaited_once()
    assert mock_ensure.await_args.kwargs.get("tenant_id") == "t-5" \
        or "t-5" in mock_ensure.await_args.args


@pytest.mark.asyncio
async def test_tenant_suspended_starts_no_workflow(consumer):
    """Regression guard: this used to start "TenantSuspensionWorkflow" — never
    @workflow.defn'd anywhere. TENANT_SUSPENDED IS published (routers/tenants.py's
    suspend_tenant), but no durable process is needed for it — AuditConsumer's
    dual-publish to prana.audit.events already gives CISO/PA audit visibility."""
    event = {"event_type": "TENANT_SUSPENDED", "tenant_id": "t-2", "reason": "nonpayment"}
    await consumer._dispatch("TENANT_SUSPENDED", event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_kek_rotated_starts_no_workflow(consumer):
    """Regression guard: this used to start "KekRotationWorkflow" — never
    @workflow.defn'd anywhere, and KEK_ROTATED is never published. Real KEK
    rotation is KMSKeyRotationWorkflow's perpetual per-tenant-iterating process,
    not a per-event workflow."""
    event = {"event_type": "KEK_ROTATED", "tenant_id": "t-3"}
    await consumer._dispatch("KEK_ROTATED", event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_running_is_idempotent(consumer):
    consumer._temporal.start_workflow.side_effect = Exception("already exists")
    event = {"event_type": "TENANT_CREATED", "tenant_id": "t-4", "domain": "co.com"}
    await consumer._dispatch("TENANT_CREATED", event)  # must not raise
