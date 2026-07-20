"""
Tests for kafka/consumers/workflow_consumer.py — Wave 7: Temporal workflow throttle.

Under a 20K batch upload, DOC_INGESTED events arrive faster than Temporal can
handle concurrent start_workflow calls. Without a semaphore, all 20K fire at once,
saturating the Temporal frontend and causing deadline errors.

The fix: asyncio.Semaphore(N) around start_workflow calls in _handle_doc_ingested,
where N = settings.max_concurrent_workflow_starts (default 50).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_consumer(max_concurrent: int = 50):
    """Build a WorkflowConsumer with mocked Temporal client and settings."""
    from kafka.consumers.workflow_consumer import WorkflowConsumer

    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.max_concurrent_workflow_starts = max_concurrent

    temporal = MagicMock()
    temporal.start_workflow = AsyncMock()

    with patch("kafka.consumers.workflow_consumer.AIOKafkaConsumer"):
        consumer = WorkflowConsumer(settings, temporal)

    return consumer, temporal


def _doc_event(i: int) -> dict:
    return {
        "event_type": "DOC_INGESTED",
        "document_id": f"doc-{i:05d}",
        "tenant_id": "tenant-1",
        "doc_type": "SALARY_SLIP",
        "doc_period": "2024-04",
        "s3_key": f"staging/abc1/tenant-1/doc-{i:05d}.pdf",
        "s3_bucket": "prana-staging",
    }


@pytest.mark.asyncio
async def test_workflow_consumer_has_semaphore_attribute():
    """
    WorkflowConsumer must expose a _wf_semaphore attribute (asyncio.Semaphore).
    RED: fails until __init__ creates the semaphore.
    """
    consumer, _ = _make_consumer(max_concurrent=50)
    assert hasattr(consumer, "_wf_semaphore"), (
        "WorkflowConsumer must have a _wf_semaphore attribute. "
        "It caps concurrent Temporal start_workflow calls during burst ingest."
    )
    assert isinstance(consumer._wf_semaphore, asyncio.Semaphore), (
        "_wf_semaphore must be an asyncio.Semaphore"
    )


@pytest.mark.asyncio
async def test_semaphore_limit_read_from_settings():
    """
    The semaphore size must be taken from settings.max_concurrent_workflow_starts,
    not hardcoded. Different tenants/envs may need different concurrency limits.
    RED: fails if the limit is always 50 regardless of settings.
    """
    consumer_low, _ = _make_consumer(max_concurrent=5)
    consumer_high, _ = _make_consumer(max_concurrent=100)

    # asyncio.Semaphore stores its initial value in _value
    assert consumer_low._wf_semaphore._value == 5, (
        "Semaphore value must equal settings.max_concurrent_workflow_starts=5"
    )
    assert consumer_high._wf_semaphore._value == 100, (
        "Semaphore value must equal settings.max_concurrent_workflow_starts=100"
    )


@pytest.mark.asyncio
async def test_concurrent_doc_ingested_respects_semaphore():
    """
    When 100 DOC_INGESTED events fire simultaneously, the semaphore must ensure
    at most N concurrent Temporal start_workflow calls are in-flight at any time.

    Mechanism: replace start_workflow with a slow coroutine (100ms). Count the
    peak concurrent callers — it must never exceed the semaphore limit.

    RED: fails until _handle_doc_ingested acquires the semaphore before starting workflows.
    """
    LIMIT = 10
    consumer, temporal = _make_consumer(max_concurrent=LIMIT)

    peak_concurrent = 0
    current_concurrent = 0

    async def slow_start_workflow(*args, **kwargs):
        nonlocal peak_concurrent, current_concurrent
        current_concurrent += 1
        peak_concurrent = max(peak_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        current_concurrent -= 1

    temporal.start_workflow.side_effect = slow_start_workflow

    # Fire 30 events concurrently
    tasks = [
        asyncio.create_task(consumer._handle_doc_ingested(_doc_event(i)))
        for i in range(30)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    assert peak_concurrent <= LIMIT, (
        f"Peak concurrent Temporal calls was {peak_concurrent}, "
        f"but semaphore limit is {LIMIT}. "
        "Semaphore is not being acquired in _handle_doc_ingested."
    )


# ── DOMAIN_VERIFICATION_REQUESTED — tenant onboarding never actually started ──
# tenants.py's create_tenant already published this event, but nothing ever
# consumed it, so DomainVerificationWorkflow never actually ran for a new tenant.

@pytest.mark.asyncio
async def test_domain_verification_requested_starts_workflow():
    consumer, temporal = _make_consumer()
    event = {
        "event_type": "DOMAIN_VERIFICATION_REQUESTED",
        "tenant_id": "tenant-xyz",
        "domain": "acme.com",
        "workflow_id": "domain-verify-tenant-xyz",
    }

    await consumer._handle_domain_verification_requested(event)

    temporal.start_workflow.assert_called_once()
    call = temporal.start_workflow.call_args
    assert call.kwargs["id"] == "domain-verify-tenant-xyz"
    args_payload = call.args[1]
    assert args_payload["tenant_id"] == "tenant-xyz"
    assert args_payload["domain"] == "acme.com"


@pytest.mark.asyncio
async def test_domain_verification_requested_is_idempotent_on_already_started():
    consumer, temporal = _make_consumer()
    temporal.start_workflow = AsyncMock(side_effect=Exception("Workflow already started"))
    event = {
        "tenant_id": "tenant-xyz", "domain": "acme.com",
        "workflow_id": "domain-verify-tenant-xyz",
    }

    await consumer._handle_domain_verification_requested(event)  # must not raise
