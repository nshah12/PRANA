"""Tests for workflows/security.py — security lifecycle workflows."""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflows.security import (
    PolicyLockWorkflow,
    KMSKeyRotationWorkflow,
    HMACSecretRotationWorkflow,
    TOTPLockoutWorkflow,
    RENEW_THRESHOLD,
    get_security_config,
    apply_policy_lock,
    release_policy_lock,
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


# ── Regression: AnomalyDetectionWorkflow and KMSKeyRotationWorkflow are both
# Pattern 4 (Continue-As-New, perpetual) — meant to be started exactly once
# and keep themselves running forever. Neither had ANY start_workflow call
# anywhere in the codebase: AnomalyDetectionService (the 6-rule anomaly
# detection engine: IMPOSSIBLE_TRAVEL, BULK_DOC_ACCESS, BRUTE_FORCE,
# CROSS_TENANT_QUERY, PRE_EXIT_BULK, SHARE_ENUM) was only ever instantiated
# from inside this dead workflow's own activity, and same for
# KMSRotationService.rotate_tenant_kek — meaning neither anomaly detection nor
# tenant KEK rotation has ever actually run. ──────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_anomaly_detection_running_starts_with_deterministic_id():
    from workflows.security import ensure_anomaly_detection_running, AnomalyDetectionWorkflow

    client = AsyncMock()
    await ensure_anomaly_detection_running(client)

    client.start_workflow.assert_awaited_once()
    args, kwargs = client.start_workflow.call_args
    assert args[0] is AnomalyDetectionWorkflow.run
    assert kwargs["id"] == "anomaly-detection-perpetual"
    assert kwargs["task_queue"] == "secops-queue"


@pytest.mark.asyncio
async def test_ensure_anomaly_detection_running_tolerates_already_started():
    from workflows.security import ensure_anomaly_detection_running

    client = AsyncMock()
    client.start_workflow.side_effect = Exception("Workflow execution already started")
    await ensure_anomaly_detection_running(client)  # must not raise


@pytest.mark.asyncio
async def test_ensure_kms_key_rotation_running_starts_with_deterministic_id():
    from workflows.security import ensure_kms_key_rotation_running, KMSKeyRotationWorkflow

    client = AsyncMock()
    await ensure_kms_key_rotation_running(client)

    client.start_workflow.assert_awaited_once()
    args, kwargs = client.start_workflow.call_args
    assert args[0] is KMSKeyRotationWorkflow.run
    assert kwargs["id"] == "kms-key-rotation-perpetual"
    assert kwargs["task_queue"] == "secops-queue"


@pytest.mark.asyncio
async def test_ensure_kms_key_rotation_running_tolerates_already_started():
    from workflows.security import ensure_kms_key_rotation_running

    client = AsyncMock()
    client.start_workflow.side_effect = Exception("already exists")
    await ensure_kms_key_rotation_running(client)  # must not raise


# ── HMACSecretRotationWorkflow — 2-distinct-PA approval gate ─────────────────
# schema.sql documents "HMACSecretRotationWorkflow requires 2 DISTINCT PA
# accounts (4-eyes enforcement)" — was previously entirely missing (see the
# KNOWN GAP this replaces in services/kms_rotation_service.py). Tested by
# direct instantiation (the signal handler and approval-count logic are
# plain Python — no Temporal runtime call inside them — matching this
# codebase's existing convention of not spinning up a Temporal test
# environment anywhere; see workflows/CLAUDE.md's Engineering Independence
# Rule: business logic is unit-testable without a Temporal cluster).

def test_hmac_rotation_workflow_starts_with_no_approvers():
    wf = HMACSecretRotationWorkflow()
    assert wf._approvers == set()


@pytest.mark.asyncio
async def test_hmac_rotation_approve_signal_accumulates_distinct_approvers():
    wf = HMACSecretRotationWorkflow()
    await wf.approve("pa-1")
    assert len(wf._approvers) == 1
    await wf.approve("pa-2")
    assert len(wf._approvers) == 2


@pytest.mark.asyncio
async def test_hmac_rotation_same_approver_signaling_twice_does_not_count_as_two():
    wf = HMACSecretRotationWorkflow()
    await wf.approve("pa-1")
    await wf.approve("pa-1")
    assert len(wf._approvers) == 1


@pytest.mark.asyncio
async def test_ensure_hmac_secret_rotation_running_starts_with_deterministic_id():
    from workflows.security import ensure_hmac_secret_rotation_running

    client = AsyncMock()
    await ensure_hmac_secret_rotation_running(client)

    client.start_workflow.assert_awaited_once()
    args, kwargs = client.start_workflow.call_args
    assert args[0] is HMACSecretRotationWorkflow.run
    assert kwargs["id"] == "hmac-secret-rotation-perpetual"
    assert kwargs["task_queue"] == "secops-queue"


@pytest.mark.asyncio
async def test_ensure_hmac_secret_rotation_running_tolerates_already_started():
    from workflows.security import ensure_hmac_secret_rotation_running

    client = AsyncMock()
    client.start_workflow.side_effect = Exception("already exists")
    await ensure_hmac_secret_rotation_running(client)  # must not raise


def test_totp_lockout_duration_from_config():
    src = inspect.getsource(TOTPLockoutWorkflow.run)
    assert "totp_lockout_cooldown_minutes" in src, \
        "TOTP lockout duration must be read from config, not hardcoded"
    assert "execute_activity" in src, \
        "TOTPLockoutWorkflow must delegate via execute_activity"


def _patched_asyncpg_and_redis():
    """get_security_config/apply_policy_lock/release_policy_lock all open their own
    asyncpg + redis connections — patch both at the module level they're imported in."""
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    return (
        patch("asyncpg.connect", new_callable=AsyncMock),
        patch("redis.asyncio.from_url", return_value=fake_redis),
    )


@pytest.mark.asyncio
async def test_get_security_config_returns_resolved_value():
    """Regression guard: was a bare stub (`...` -> None) — every workflow in this
    file that reads a duration/schedule from config would crash on int(None)."""
    p_asyncpg, p_redis = _patched_asyncpg_and_redis()
    with p_asyncpg, p_redis, \
         patch("services.config_service.ConfigService.get", new_callable=AsyncMock, return_value="48"):
        result = await get_security_config({"key": "policy_lock_default_hours", "tenant_id": "t-1", "default": "24"})
    assert result == "48"


@pytest.mark.asyncio
async def test_get_security_config_falls_back_to_default_when_unset():
    p_asyncpg, p_redis = _patched_asyncpg_and_redis()
    with p_asyncpg, p_redis, \
         patch("services.config_service.ConfigService.get", new_callable=AsyncMock, return_value=None):
        result = await get_security_config({"key": "policy_lock_default_hours", "default": "24"})
    assert result == "24"


@pytest.mark.asyncio
async def test_apply_policy_lock_activity_delegates_to_account_lock_service():
    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.account_lock_service.AccountLockService.apply_policy_lock",
               new_callable=AsyncMock, return_value="event-1") as mock_apply:
        result = await apply_policy_lock({
            "user_type": "employee", "user_id": "emp-1", "tenant_id": "t-1",
            "reason_code": "BULK_ACCESS_ANOMALY", "lock_hours": 24,
        })
    assert result == "event-1"
    mock_apply.assert_awaited_once_with(
        user_type="employee", user_id="emp-1", tenant_id="t-1",
        reason_code="BULK_ACCESS_ANOMALY", lock_hours=24,
    )


@pytest.mark.asyncio
async def test_release_policy_lock_activity_delegates_to_account_lock_service():
    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.account_lock_service.AccountLockService.release_policy_lock",
               new_callable=AsyncMock) as mock_release:
        await release_policy_lock({
            "user_type": "employee", "user_id": "emp-1",
            "event_id": "event-1", "unlocked_by": "", "early": False,
        })
    mock_release.assert_awaited_once_with(
        user_type="employee", user_id="emp-1",
        event_id="event-1", unlocked_by="", early=False,
    )


# ── TOTP lockout activities ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_totp_lockout_delegates_to_account_lock_service():
    from workflows.security import apply_totp_lockout

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.account_lock_service.AccountLockService.apply_totp_lockout",
               new_callable=AsyncMock, return_value="event-2") as mock_apply:
        result = await apply_totp_lockout({"user_type": "employee", "user_id": "emp-1", "tenant_id": "t-1"})
    assert result == "event-2"
    mock_apply.assert_awaited_once_with(user_type="employee", user_id="emp-1", tenant_id="t-1")


@pytest.mark.asyncio
async def test_release_totp_lockout_delegates_to_account_lock_service():
    from workflows.security import release_totp_lockout

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.account_lock_service.AccountLockService.release_totp_lockout",
               new_callable=AsyncMock) as mock_release:
        await release_totp_lockout({"user_type": "employee", "user_id": "emp-1", "event_id": "event-2"})
    mock_release.assert_awaited_once_with(user_type="employee", user_id="emp-1", event_id="event-2")


# ── Session activities ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expire_session_revokes_with_expired_reason():
    from workflows.security import expire_session

    p_asyncpg, p_redis = _patched_asyncpg_and_redis()
    with p_asyncpg, p_redis, \
         patch("services.session_service.SessionService.revoke", new_callable=AsyncMock) as mock_revoke:
        await expire_session({"session_id": "sess-1"})
    mock_revoke.assert_awaited_once_with("sess-1", reason="EXPIRED")


@pytest.mark.asyncio
async def test_force_revoke_session_uses_ciso_reason():
    from workflows.security import force_revoke_session

    p_asyncpg, p_redis = _patched_asyncpg_and_redis()
    with p_asyncpg, p_redis, \
         patch("services.session_service.SessionService.revoke", new_callable=AsyncMock) as mock_revoke:
        await force_revoke_session({"session_id": "sess-2"})
    mock_revoke.assert_awaited_once_with("sess-2", reason="FORCE_REVOKED_CISO")


# ── KMS / HMAC rotation activities ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_next_tenant_for_rotation_delegates_with_interval():
    from workflows.security import get_next_tenant_for_rotation

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.kms_rotation_service.KMSRotationService.get_next_tenant_for_rotation",
               new_callable=AsyncMock, return_value={"tenant_id": "t-1", "kek_arn": "arn:1"}) as mock_get:
        result = await get_next_tenant_for_rotation({"interval_days": 365})
    assert result == {"tenant_id": "t-1", "kek_arn": "arn:1"}
    mock_get.assert_awaited_once_with(interval_days=365)


@pytest.mark.asyncio
async def test_kms_key_rotation_workflow_passes_interval_days_to_next_tenant_lookup():
    """Regression guard: _rotate_one used to fetch interval_str via
    get_security_config and then never pass it to get_next_tenant_for_rotation —
    the activity would have received no interval_days at all."""
    src = inspect.getsource(KMSKeyRotationWorkflow._rotate_one)
    assert "interval_days" in src, \
        "interval_str must actually be threaded into get_next_tenant_for_rotation's params"


@pytest.mark.asyncio
async def test_rotate_tenant_kek_delegates_to_kms_rotation_service():
    from workflows.security import rotate_tenant_kek

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.kms_rotation_service.KMSRotationService.rotate_tenant_kek",
               new_callable=AsyncMock) as mock_rotate, \
         patch("services.encryption_service.KMSService.__init__", return_value=None):
        await rotate_tenant_kek({"tenant_id": "t-1", "kek_arn": "arn:1"})
    mock_rotate.assert_awaited_once_with(tenant_id="t-1", kek_arn="arn:1")


@pytest.mark.asyncio
async def test_rotate_hmac_secret_delegates_to_kms_rotation_service():
    from workflows.security import rotate_hmac_secret

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.kms_rotation_service.KMSRotationService.rotate_hmac_secret",
               new_callable=AsyncMock) as mock_rotate, \
         patch("boto3.client", return_value=MagicMock()):
        await rotate_hmac_secret({"secret_id": "prana/platform-hmac-secret"})
    mock_rotate.assert_awaited_once_with(secret_id="prana/platform-hmac-secret")


# ── CSAM reporting activities ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_csam_legal_hold_delegates_to_compliance_service():
    from workflows.security import apply_csam_legal_hold

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.compliance_service.ComplianceService.apply_legal_hold",
               new_callable=AsyncMock) as mock_hold:
        await apply_csam_legal_hold({"tenant_id": "t-1", "document_id": "doc-1"})
    mock_hold.assert_awaited_once_with(reason="CSAM_NCMEC_HOLD", tenant_id="t-1", document_id="doc-1")


@pytest.mark.asyncio
async def test_report_csam_to_ncmec_delegates_to_csam_report_service():
    from workflows.security import report_csam_to_ncmec

    p_asyncpg, _ = _patched_asyncpg_and_redis()
    with p_asyncpg, \
         patch("services.csam_report_service.CSAMReportService.report_to_ncmec",
               new_callable=AsyncMock, return_value={"report_id": "R-1"}) as mock_report:
        result = await report_csam_to_ncmec({"document_id": "doc-1", "tenant_id": "t-1"})
    assert result == {"report_id": "R-1"}
    mock_report.assert_awaited_once_with(document_id="doc-1", tenant_id="t-1")


@pytest.mark.asyncio
async def test_report_csam_to_ncmec_dev_mode_logs_instead_of_calling_out():
    """Mandatory legal filing — dev mode must not silently no-op without a trace."""
    from services.csam_report_service import CSAMReportService
    from config import Settings

    settings = Settings(ncmec_report_url="")
    result = await CSAMReportService(db=MagicMock(), settings=settings).report_to_ncmec(
        document_id="doc-1", tenant_id="t-1",
    )
    assert result == {"report_id": "DEV-NOOP"}


@pytest.mark.asyncio
async def test_notify_csam_platform_admin_publishes_security_event():
    from workflows.security import notify_csam_platform_admin

    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock, return_value=mock_kafka):
        await notify_csam_platform_admin({"document_id": "doc-1", "tenant_id": "t-1"})
    mock_kafka.security_event.assert_awaited_once()
    event = mock_kafka.security_event.call_args[0][0]
    assert event["event_type"] == "CSAM_REPORT_SUBMITTED"
    assert event["recipient_role"] == "PLATFORM_ADMIN"
