"""Tests for SecurityConsumer — prana.security.events"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def redis():
    r = AsyncMock()
    r.publish = AsyncMock()
    return r


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool, redis):
    from kafka.consumers.security_consumer import SecurityConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return SecurityConsumer(settings, db_pool=pool, temporal_client=temporal, redis=redis)


@pytest.mark.asyncio
async def test_anomaly_detected_publishes_sse_alert(consumer, db_pool, redis):
    _, conn = db_pool
    conn.execute = AsyncMock()
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1",
             "user_id": "u-1", "anomaly_type": "UNUSUAL_ACCESS"}
    await consumer._dispatch("ANOMALY_DETECTED", event)
    redis.publish.assert_awaited_once()
    channel = redis.publish.call_args[0][0]
    assert "sse:tenant:t-1:alerts" == channel


@pytest.mark.asyncio
async def test_csam_detected_starts_reporting_workflow(consumer):
    event = {"event_type": "CSAM_DETECTED", "tenant_id": "t-1", "document_id": "d-1"}
    await consumer._dispatch("CSAM_DETECTED", event)
    consumer._temporal.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_locked_publishes_sse_alert(consumer, db_pool, redis):
    _, conn = db_pool
    conn.execute = AsyncMock()
    event = {"event_type": "ACCOUNT_LOCKED", "tenant_id": "t-1", "user_id": "u-2"}
    await consumer._dispatch("ACCOUNT_LOCKED", event)
    redis.publish.assert_awaited()


# ── _handle_anomaly — real incident table, not the phantom security_incident ────

@pytest.mark.asyncio
async def test_anomaly_writes_to_real_incident_table_not_phantom_table(consumer, db_pool):
    """Regression guard: security_incident does not exist in schema.sql — this consumer
    must never reference it. See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §4."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "BULK_DOC_ACCESS",
             "severity": "P1", "anomaly_id": "anom-1"}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value="incident-1") as mock_auto_create:
        await consumer._dispatch("ANOMALY_DETECTED", event)

    mock_auto_create.assert_awaited_once_with(
        anomaly_id="anom-1", tenant_id="t-1", rule_name="BULK_DOC_ACCESS",
        severity="P1", assigned_ciso_id=None,
    )
    for c in conn.execute.call_args_list:
        assert "security_incident" not in c.args[0]


@pytest.mark.asyncio
async def test_anomaly_uses_explicit_severity_when_present(consumer, db_pool):
    """If the publisher already resolved severity (the new detection engine does), trust it
    rather than re-resolving via policy."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "BRUTE_FORCE",
             "severity": "P0", "anomaly_id": "anom-2"}

    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock) as mock_resolve, \
         patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    mock_resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_anomaly_resolves_severity_via_policy_when_missing(consumer, db_pool):
    """This is the fix for the security_consumer (P3) vs notif_consumer (P2) default
    disagreement — both now resolve via the same shared policy lookup."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "SOME_NEW_RULE",
             "anomaly_id": "anom-3"}  # no "severity" key

    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P2") as mock_resolve, \
         patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None) as mock_auto_create:
        await consumer._dispatch("ANOMALY_DETECTED", event)

    mock_resolve.assert_awaited_once_with(domain="ANOMALY_RULE", value="SOME_NEW_RULE")
    mock_auto_create.assert_awaited_once_with(
        anomaly_id="anom-3", tenant_id="t-1", rule_name="SOME_NEW_RULE",
        severity="P2", assigned_ciso_id=None,
    )


@pytest.mark.asyncio
async def test_anomaly_persists_the_anomaly_event_row_idempotently(consumer, db_pool):
    """Event-driven anomalies (published by an HTTP-handler-triggered guard, not a
    Temporal activity or the batch scanner) have no other writer for anomaly_event —
    this consumer must persist the row itself, keyed by the publisher-supplied
    anomaly_id so redelivery doesn't create duplicates."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "CROSS_TENANT_QUERY",
             "severity": "P0", "anomaly_id": "anom-4", "actor_id": "oa-9",
             "event_metadata": {"resource_id": "doc-1"}}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    insert_call = next(c for c in conn.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "ON CONFLICT" in insert_call.args[0]
    assert "anom-4" in insert_call.args
    assert "CROSS_TENANT_QUERY" in insert_call.args
    assert "P0" in insert_call.args
    assert "oa-9" in insert_call.args


# ── Auto-lock trigger — config-gated, ships OFF by default ──────────────────

@pytest.mark.asyncio
async def test_auto_lock_skipped_when_config_flag_disabled(consumer, db_pool):
    """Both bulk_access_auto_lock_enabled and brute_force_auto_lock_enabled seed
    false — this is the ship-safe default and must be honoured."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "BULK_DOC_ACCESS",
             "severity": "P1", "anomaly_id": "anom-5", "actor_id": "oa-1", "actor_user_type": "oa_user"}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None), \
         patch("services.config_service.ConfigService.get_bool",
               new_callable=AsyncMock, return_value=False):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_lock_starts_policy_lock_workflow_when_enabled(consumer, db_pool):
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "BULK_DOC_ACCESS",
             "severity": "P1", "anomaly_id": "anom-6", "actor_id": "oa-1", "actor_user_type": "oa_user"}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None), \
         patch("services.config_service.ConfigService.get_bool",
               new_callable=AsyncMock, return_value=True):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    consumer._temporal.start_workflow.assert_awaited_once()
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "PolicyLockWorkflow"
    assert call.args[1] == {
        "user_type": "oa_user", "user_id": "oa-1",
        "tenant_id": "t-1", "reason_code": "BULK_ACCESS_ANOMALY",
    }
    assert call.kwargs["task_queue"] == "auth-queue"
    assert call.kwargs["id"] == "policy-lock-BULK_DOC_ACCESS-oa-1"


@pytest.mark.asyncio
async def test_auto_lock_skipped_for_third_party_actor_no_lockable_account(consumer, db_pool):
    """THIRD_PARTY actors (HRMS API keys) have no local account row to lock —
    anomaly_detection_service.py sends actor_user_type=None for these."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "BULK_DOC_ACCESS",
             "severity": "P1", "anomaly_id": "anom-7", "actor_id": "hrms-key-1", "actor_user_type": None}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None), \
         patch("services.config_service.ConfigService.get_bool",
               new_callable=AsyncMock, return_value=True):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_lock_skipped_for_rule_not_in_auto_lock_list(consumer, db_pool):
    """OFF_HOURS_ACCESS/IMPOSSIBLE_TRAVEL/SHARE_ENUM/PRE_EXIT_BULK are not
    auto-lockable — only BULK_DOC_ACCESS and BRUTE_FORCE are."""
    _, conn = db_pool
    event = {"event_type": "ANOMALY_DETECTED", "tenant_id": "t-1", "rule_name": "OFF_HOURS_ACCESS",
             "severity": "P2", "anomaly_id": "anom-8", "actor_id": "emp-1", "actor_user_type": "employee"}

    with patch("services.incident_service.IncidentService.auto_create_for_anomaly",
               new_callable=AsyncMock, return_value=None), \
         patch("services.config_service.ConfigService.get_bool",
               new_callable=AsyncMock, return_value=True):
        await consumer._dispatch("ANOMALY_DETECTED", event)

    consumer._temporal.start_workflow.assert_not_awaited()
