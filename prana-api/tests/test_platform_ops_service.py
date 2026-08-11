"""Tests for services/platform_ops_service.py — implements the previously-stub
activities in workflows/platform_ops.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.platform_ops_service import PlatformOpsService


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _db(fetch_return=None, fetchval_return=None):
    db = AsyncMock()
    db.fetch.return_value = fetch_return or []
    db.fetchval.return_value = fetchval_return
    db.transaction = lambda: _FakeTxn()
    return db


# ── collect/write platform summary ────────────────────────────────────────

@pytest.mark.asyncio
async def test_collect_platform_metrics_returns_rows():
    tenant_id = uuid.uuid4()
    db = _db(fetch_return=[
        {"tenant_id": tenant_id, "region": "ap-south-1", "vault_health_pct": 82.5,
         "active_threats": 2, "kek_age_days": 30},
    ])
    result = await PlatformOpsService(db).collect_platform_metrics()
    assert result["rows"][0]["tenant_id"] == tenant_id
    assert result["rows"][0]["vault_health_pct"] == 82.5


@pytest.mark.asyncio
async def test_write_platform_summary_upserts_each_row():
    db = _db()
    tenant_id = uuid.uuid4()
    await PlatformOpsService(db).write_platform_summary([
        {"region": "ap-south-1", "tenant_id": tenant_id, "vault_health_pct": 90,
         "active_threats": 0, "kek_age_days": 10},
    ])
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO pa_platform_summary" in c.args[0])
    assert "ON CONFLICT" in insert_call.args[0]
    assert tenant_id in insert_call.args


# ── KMS health ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_kms_key_health_all_healthy_when_no_errors():
    db = _db(fetch_return=[{"tenant_id": uuid.uuid4(), "kek_arn": "arn:1"}])
    kms = MagicMock()
    result = await PlatformOpsService(db, kms_client=kms).verify_kms_key_health()
    assert result["all_healthy"] is True
    kms.describe_key.assert_called_once_with(KeyId="arn:1")


@pytest.mark.asyncio
async def test_verify_kms_key_health_reports_failures():
    db = _db(fetch_return=[{"tenant_id": uuid.uuid4(), "kek_arn": "arn:bad"}])
    kms = MagicMock()
    kms.describe_key.side_effect = Exception("KeyUnavailableException")
    result = await PlatformOpsService(db, kms_client=kms).verify_kms_key_health()
    assert result["all_healthy"] is False
    assert result["failures"][0]["kek_arn"] == "arn:bad"


@pytest.mark.asyncio
async def test_alert_kms_key_issue_publishes_platform_event():
    db = _db()
    kafka = AsyncMock()
    await PlatformOpsService(db, kafka=kafka).alert_kms_key_issue([{"tenant_id": "t-1"}])
    kafka.platform_event.assert_awaited_once()
    assert kafka.platform_event.call_args[0][0]["event_type"] == "KMS_HEALTH_FAILED"


# ── Storage quota ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_tenant_storage_quotas_flags_over_threshold():
    tenant_id = uuid.uuid4()
    quota_bytes = 50 * 1024 ** 3
    db = _db(fetch_return=[
        {"tenant_id": tenant_id, "storage_quota_gb": 50, "used_bytes": int(quota_bytes * 0.85)},
    ])
    result = await PlatformOpsService(db).check_tenant_storage_quotas()
    assert len(result) == 1
    assert result[0]["threshold"] == "WARNING"


@pytest.mark.asyncio
async def test_check_tenant_storage_quotas_critical_at_95_pct():
    tenant_id = uuid.uuid4()
    quota_bytes = 50 * 1024 ** 3
    db = _db(fetch_return=[
        {"tenant_id": tenant_id, "storage_quota_gb": 50, "used_bytes": int(quota_bytes * 0.97)},
    ])
    result = await PlatformOpsService(db).check_tenant_storage_quotas()
    assert result[0]["threshold"] == "CRITICAL"


@pytest.mark.asyncio
async def test_check_tenant_storage_quotas_skips_tenants_under_80_pct():
    tenant_id = uuid.uuid4()
    quota_bytes = 50 * 1024 ** 3
    db = _db(fetch_return=[
        {"tenant_id": tenant_id, "storage_quota_gb": 50, "used_bytes": int(quota_bytes * 0.5)},
    ])
    result = await PlatformOpsService(db).check_tenant_storage_quotas()
    assert result == []


# ── Staging cleanup ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_purge_stale_staging_objects_deletes_only_old_ones():
    now = datetime.now(timezone.utc)
    s3 = MagicMock()
    s3.get_paginator.return_value.paginate.return_value = [{
        "Contents": [
            {"Key": "old.pdf", "LastModified": now - timedelta(days=10)},
            {"Key": "new.pdf", "LastModified": now - timedelta(days=1)},
        ]
    }]
    db = _db()
    result = await PlatformOpsService(db, s3_client=s3).purge_stale_staging_objects(
        staging_bucket="prana-staging-dev", older_than_days=7,
    )
    assert result["deleted_count"] == 1
    s3.delete_objects.assert_called_once_with(
        Bucket="prana-staging-dev", Delete={"Objects": [{"Key": "old.pdf"}]},
    )


@pytest.mark.asyncio
async def test_purge_stale_staging_objects_noop_without_s3_client():
    db = _db()
    result = await PlatformOpsService(db, s3_client=None).purge_stale_staging_objects(
        staging_bucket="b", older_than_days=7,
    )
    assert result == {"deleted_count": 0}


# ── Webhook delivery ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_webhook_success_marks_delivered():
    db = _db()
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await PlatformOpsService(db).deliver_webhook(
            delivery_id="d-1", tenant_id="t-1", webhook_url="https://hrms.example/hook",
            event_type="DOC_ROUTED", payload={"document_id": "doc-1"},
        )
    assert result["success"] is True
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO webhook_delivery_log" in c.args[0])
    assert "DELIVERED" in insert_call.args


@pytest.mark.asyncio
async def test_deliver_webhook_network_failure_leaves_pending_for_retry():
    db = _db()
    with patch("httpx.AsyncClient", side_effect=ConnectionError("refused")):
        result = await PlatformOpsService(db).deliver_webhook(
            delivery_id="d-2", tenant_id="t-1", webhook_url="https://hrms.example/hook",
            event_type="DOC_ROUTED", payload={},
        )
    assert result["success"] is False
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO webhook_delivery_log" in c.args[0])
    assert "PENDING" in insert_call.args[0]


@pytest.mark.asyncio
async def test_mark_webhook_failed_updates_status():
    db = _db()
    await PlatformOpsService(db).mark_webhook_failed("d-1")
    db.execute.assert_awaited_once_with(
        "UPDATE webhook_delivery_log SET status='FAILED' WHERE delivery_id=$1", "d-1",
    )


def test_platform_ops_service_has_no_notification_delivery_methods():
    """NotificationDeliveryWorkflow was removed 2026-08-10 — dead code, nothing ever
    started it. Real notification delivery happens via CommunicationHubConsumer's
    per-channel consumers directly. This guards against silent reintroduction.
    """
    assert not hasattr(PlatformOpsService, "deliver_notification")
    assert not hasattr(PlatformOpsService, "deliver_notification_fallback")


# ── Storage expansion ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_storage_expansion_request_inserts_row_and_returns_id():
    request_id = uuid.uuid4()
    db = _db(fetchval_return=request_id)
    kafka = AsyncMock()
    result = await PlatformOpsService(db, kafka=kafka).notify_storage_expansion_request(
        tenant_id="t-1", current_gb=50, requested_gb=100, reason="growth",
    )
    assert result == str(request_id)
    kafka.platform_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_storage_expansion_updates_tenant_quota_and_request_status():
    db = _db()
    await PlatformOpsService(db).apply_storage_expansion(
        tenant_id="t-1", request_id="req-1", requested_gb=100, decided_by="pa-1",
    )
    quota_call = next(c for c in db.execute.call_args_list if "UPDATE tenant SET storage_quota_gb" in c.args[0])
    assert quota_call.args[1] == 100
    status_call = next(c for c in db.execute.call_args_list if "status='APPROVED'" in c.args[0])
    assert status_call.args[1] == "pa-1"


@pytest.mark.asyncio
async def test_reject_storage_expansion_updates_status_only():
    db = _db()
    await PlatformOpsService(db).reject_storage_expansion(request_id="req-1", decided_by="pa-1")
    db.execute.assert_awaited_once()
    assert "REJECTED" in db.execute.call_args.args[0]


# ── Onboarding SLA escalation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_escalate_onboarding_review_publishes_platform_event():
    db = _db()
    kafka = AsyncMock()
    await PlatformOpsService(db, kafka=kafka).escalate_onboarding_review(tenant_id="t-1")
    kafka.platform_event.assert_awaited_once()
    assert kafka.platform_event.call_args[0][0]["event_type"] == "ONBOARDING_REVIEW_SLA_BREACH"
