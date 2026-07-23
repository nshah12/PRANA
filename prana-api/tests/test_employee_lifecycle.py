"""
Tests for workflows/employee_lifecycle.py — Temporal workflow shells + activities.

Structural tests verify architectural constraints without running a Temporal cluster:
  - Workflow @run methods are thin shells (<20 lines), delegate via execute_activity
  - Durations come from get_lifecycle_config, never hardcoded
Activity tests verify each activity delegates to services/employee_lifecycle_service.py
(zero Temporal imports there) via its own short-lived DB connection — the same pattern
used by workflows/vault_shares.py's real activity implementations.
"""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflows.employee_lifecycle import (
    EmployeeExitWorkflow,
    PushWindowExpiryWorkflow,
    NomineeAccessWorkflow,
    freeze_employee_vault,
    notify_exit_employee,
    start_retention_workflow,
    start_push_window_expiry_workflow,
    close_push_window,
    provision_vault,
    send_vault_welcome,
    recompute_vault_completeness,
    grant_nominee_access,
    revoke_nominee_access,
    reconcile_rejoining_employee,
    flag_dormant_account,
    get_lifecycle_config,
    send_alumni_consent_prompt,
)


def _get_source_lines(method) -> list[str]:
    source = inspect.getsource(method)
    return [l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]


# ── EmployeeExitWorkflow ──────────────────────────────────────────────────────

def test_employee_exit_workflow_uses_durable_timer():
    source = inspect.getsource(EmployeeExitWorkflow.run)
    assert "execute_activity" in source, "EmployeeExitWorkflow must use execute_activity"
    assert "INSERT" not in source, "No SQL in workflow shell"
    assert "SELECT" not in source, "No SQL in workflow shell"


def test_employee_exit_workflow_is_thin_shell():
    lines = _get_source_lines(EmployeeExitWorkflow.run)
    assert len(lines) <= 20, f"EmployeeExitWorkflow.run has {len(lines)} lines — must be <20"


def test_employee_exit_workflow_calls_freeze_and_notify():
    run_source = inspect.getsource(EmployeeExitWorkflow.run)
    for name in ("freeze_employee_vault", "notify_exit_employee",
                 "_start_detached_followups", "send_alumni_consent_prompt"):
        assert name in run_source
    followups_source = inspect.getsource(EmployeeExitWorkflow._start_detached_followups)
    assert "start_retention_workflow" in followups_source


def test_employee_exit_workflow_starts_push_window_expiry():
    """Regression: PushWindowExpiryWorkflow's own docstring says the employer
    push window closes 30 days post-exit, but nothing anywhere started this
    workflow (same detached-start shape as start_retention_workflow, right next
    to it in this file) — close_push_window was only ever reachable from
    inside this never-started workflow, so employer pushes never actually
    stopped after the grace period."""
    source = inspect.getsource(EmployeeExitWorkflow._start_detached_followups)
    assert "start_push_window_expiry_workflow" in source


@pytest.mark.asyncio
async def test_start_push_window_expiry_workflow_starts_on_admin_queue():
    with patch("temporalio.client.Client.connect", new_callable=AsyncMock) as mock_connect:
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client
        await start_push_window_expiry_workflow({"employee_uuid": "emp-12", "tenant_id": "t-1"})
    call = mock_client.start_workflow.call_args
    assert call.args[0] == "PushWindowExpiryWorkflow"
    assert call.kwargs["id"] == "push-window-expiry-emp-12"
    assert call.kwargs["task_queue"] == "admin-queue"


@pytest.mark.asyncio
async def test_start_push_window_expiry_workflow_is_idempotent():
    with patch("temporalio.client.Client.connect", new_callable=AsyncMock) as mock_connect:
        mock_client = AsyncMock()
        mock_client.start_workflow.side_effect = Exception("Workflow already exists")
        mock_connect.return_value = mock_client
        await start_push_window_expiry_workflow({"employee_uuid": "emp-13", "tenant_id": "t-1"})  # must not raise


# ── PushWindowExpiryWorkflow ──────────────────────────────────────────────────

def test_push_window_expiry_duration_from_config():
    source = inspect.getsource(PushWindowExpiryWorkflow.run)
    assert "get_lifecycle_config" in source, "Duration must come from get_lifecycle_config activity"
    assert "workflow.sleep" in source, "Must use durable Temporal sleep, not asyncio.sleep"
    assert "timedelta(days=30)" not in source, "Duration must not be hardcoded as 30 days"


def test_push_window_expiry_workflow_is_thin_shell():
    lines = _get_source_lines(PushWindowExpiryWorkflow.run)
    assert len(lines) <= 20, f"PushWindowExpiryWorkflow.run has {len(lines)} lines — must be <20"


# ── NomineeAccessWorkflow ─────────────────────────────────────────────────────

def test_nominee_access_workflow_reads_window_from_config():
    source = inspect.getsource(NomineeAccessWorkflow.run)
    assert "get_lifecycle_config" in source
    assert "nominee_access_window_days" in source
    assert "window_days" in source, "grant_nominee_access must receive the resolved window_days"


# ── Activity implementations — real bodies, previously bare stubs ────────────

@pytest.mark.asyncio
async def test_freeze_employee_vault_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.freeze_employee_vault",
               new_callable=AsyncMock) as mock_freeze:
        await freeze_employee_vault({"employee_uuid": "emp-1", "tenant_id": "t-1"})
    mock_freeze.assert_awaited_once_with(employee_uuid="emp-1", tenant_id="t-1")


@pytest.mark.asyncio
async def test_close_push_window_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.close_push_window",
               new_callable=AsyncMock) as mock_close:
        await close_push_window({"employee_uuid": "emp-2", "tenant_id": "t-1"})
    mock_close.assert_awaited_once_with(employee_uuid="emp-2", tenant_id="t-1")


@pytest.mark.asyncio
async def test_provision_vault_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.provision_vault",
               new_callable=AsyncMock) as mock_provision:
        await provision_vault({"employee_user_id": "eu-3"})
    mock_provision.assert_awaited_once_with(employee_user_id="eu-3")


@pytest.mark.asyncio
async def test_recompute_vault_completeness_delegates_and_returns_result():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.recompute_vault_completeness",
               new_callable=AsyncMock, return_value={"vault_completeness": 75.0}) as mock_recompute:
        result = await recompute_vault_completeness({"employee_uuid": "emp-4", "tenant_id": "t-1"})
    mock_recompute.assert_awaited_once_with(employee_uuid="emp-4", tenant_id="t-1")
    assert result == {"vault_completeness": 75.0}


@pytest.mark.asyncio
async def test_grant_nominee_access_delegates_with_int_window_days():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.grant_nominee_access",
               new_callable=AsyncMock) as mock_grant:
        await grant_nominee_access({"employee_uuid": "emp-5", "tenant_id": "t-1", "window_days": "90"})
    mock_grant.assert_awaited_once_with(employee_uuid="emp-5", tenant_id="t-1", window_days=90)


@pytest.mark.asyncio
async def test_revoke_nominee_access_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.revoke_nominee_access",
               new_callable=AsyncMock) as mock_revoke:
        await revoke_nominee_access({"employee_uuid": "emp-6", "tenant_id": "t-1"})
    mock_revoke.assert_awaited_once_with(employee_uuid="emp-6", tenant_id="t-1")


@pytest.mark.asyncio
async def test_reconcile_rejoining_employee_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.reconcile_rejoining_employee",
               new_callable=AsyncMock) as mock_reconcile:
        await reconcile_rejoining_employee({"employee_uuid": "emp-7", "tenant_id": "t-1"})
    mock_reconcile.assert_awaited_once_with(employee_uuid="emp-7", tenant_id="t-1")


@pytest.mark.asyncio
async def test_flag_dormant_account_delegates_to_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.employee_lifecycle_service.EmployeeLifecycleService.flag_dormant_account",
               new_callable=AsyncMock) as mock_flag:
        await flag_dormant_account({"employee_user_id": "eu-8", "tenant_id": "t-1"})
    mock_flag.assert_awaited_once_with(employee_user_id="eu-8", tenant_id="t-1")


def _fake_redis():
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    return fake_redis


@pytest.mark.asyncio
async def test_get_lifecycle_config_reads_via_config_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("redis.asyncio.from_url", return_value=_fake_redis()), \
         patch("services.config_service.ConfigService.get",
               new_callable=AsyncMock, return_value="45") as mock_get:
        result = await get_lifecycle_config({"key": "dormancy_threshold_days", "tenant_id": "t-1", "default": "365"})
    mock_get.assert_awaited_once_with("dormancy_threshold_days", "t-1")
    assert result == "45"


@pytest.mark.asyncio
async def test_get_lifecycle_config_falls_back_to_default_when_unset():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("redis.asyncio.from_url", return_value=_fake_redis()), \
         patch("services.config_service.ConfigService.get",
               new_callable=AsyncMock, return_value=None):
        result = await get_lifecycle_config({"key": "dormancy_threshold_days", "tenant_id": "t-1", "default": "365"})
    assert result == "365"


@pytest.mark.asyncio
async def test_notify_exit_employee_resolves_recipient_from_employee_uuid():
    """EMPLOYEE_EXITED (routers/employees.py mark_alumni) only carries employee_uuid —
    this activity must resolve employee_user_id itself rather than assume it's in params."""
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_db = mock_connect.return_value
        mock_db.fetchrow = AsyncMock(return_value={"employee_user_id": "eu-9"})
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka

        await notify_exit_employee({"employee_uuid": "emp-9", "tenant_id": "t-1"})

    mock_kafka.publish.assert_awaited_once()
    topic, payload = mock_kafka.publish.call_args.args
    assert topic == "prana.notifications"
    assert payload["recipient_id"] == "eu-9"
    assert payload["event_type"] == "EMPLOYEE_EXITED"


@pytest.mark.asyncio
async def test_send_vault_welcome_uses_rejoin_template_when_flagged():
    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka
        await send_vault_welcome({"employee_user_id": "eu-10", "tenant_id": "t-1", "rejoin": True})
    payload = mock_kafka.publish.call_args.args[1]
    assert payload["template_id"] == "VAULT_WELCOME_REJOIN"


@pytest.mark.asyncio
async def test_send_vault_welcome_uses_first_time_template_by_default():
    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka
        await send_vault_welcome({"employee_user_id": "eu-11", "tenant_id": "t-1"})
    payload = mock_kafka.publish.call_args.args[1]
    assert payload["template_id"] == "VAULT_WELCOME"


@pytest.mark.asyncio
async def test_start_retention_workflow_starts_on_compliance_queue():
    with patch("temporalio.client.Client.connect", new_callable=AsyncMock) as mock_connect:
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client
        await start_retention_workflow({"employee_uuid": "emp-12", "tenant_id": "t-1"})
    call = mock_client.start_workflow.call_args
    assert call.args[0] == "RetentionWorkflow"
    assert call.kwargs["id"] == "retention-employee-emp-12"
    assert call.kwargs["task_queue"] == "compliance-queue"


@pytest.mark.asyncio
async def test_start_retention_workflow_is_idempotent():
    with patch("temporalio.client.Client.connect", new_callable=AsyncMock) as mock_connect:
        mock_client = AsyncMock()
        mock_client.start_workflow.side_effect = Exception("Workflow already exists")
        mock_connect.return_value = mock_client
        await start_retention_workflow({"employee_uuid": "emp-13", "tenant_id": "t-1"})  # must not raise


@pytest.mark.asyncio
async def test_send_alumni_consent_prompt_resolves_recipient_from_employee_uuid():
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_db = mock_connect.return_value
        mock_db.fetchrow = AsyncMock(return_value={"employee_user_id": "eu-14"})
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka

        await send_alumni_consent_prompt({"employee_uuid": "emp-14", "tenant_id": "t-1"})

    payload = mock_kafka.publish.call_args.args[1]
    assert payload["recipient_id"] == "eu-14"
    assert payload["template_id"] == "ALUMNI_CONSENT_PROMPT"
