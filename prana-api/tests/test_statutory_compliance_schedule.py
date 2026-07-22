"""Tests for workflows/compliance.py's StatutoryComplianceWorkflow schedule registration.

Regression: StatutoryComplianceWorkflow's own docstring claims "Pattern 3 —
Temporal Schedule (created at startup by worker.py ensure_schedules())" with a
per-tenant schedule ID ("statutory-compliance-{tenant_id}") and cadence from
platform_config.statutory_compliance_check_hour — but no such function existed
anywhere in worker.py, no config key existed, and nothing ever triggered it.
Same shape as workflows/hrms_sync_schedule.py's ensure_hrms_schedules: one
Temporal Schedule per ACTIVE tenant, idempotent create-or-update.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

TENANT_A = uuid4()
TENANT_B = uuid4()

ALL_TENANTS = [
    {"tenant_id": TENANT_A, "status": "ACTIVE"},
    {"tenant_id": TENANT_B, "status": "SUSPENDED"},
]


@pytest.fixture
def mock_db():
    """Real SQL filters WHERE status='ACTIVE' — mirror that (see
    workflows/hrms_sync_schedule.py's test fixture for the same reasoning)."""
    db = AsyncMock()
    rows = []
    for t in ALL_TENANTS:
        if t["status"] != "ACTIVE":
            continue
        row = MagicMock()
        row.__getitem__ = lambda s, k, t=t: t[k]
        rows.append(row)
    db.fetch = AsyncMock(return_value=rows)
    return db


@pytest.fixture
def mock_temporal():
    from temporalio.service import RPCError, RPCStatusCode

    tc = MagicMock()
    handle = MagicMock()
    handle.describe = AsyncMock(side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
    tc.get_schedule_handle = MagicMock(return_value=handle)
    tc.create_schedule = AsyncMock()
    return tc


@pytest.mark.asyncio
async def test_active_tenant_gets_statutory_compliance_schedule(mock_db, mock_temporal):
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec
    from workflows.compliance import (
        StatutoryComplianceWorkflow, ensure_statutory_compliance_schedules, _statutory_schedule_id,
    )

    await ensure_statutory_compliance_schedules(
        db=mock_db, temporal_client=mock_temporal, cron_expression="30 0 * * *",
    )

    mock_temporal.create_schedule.assert_awaited_once()
    schedule_id, schedule = mock_temporal.create_schedule.await_args.args[:2]
    assert schedule_id == _statutory_schedule_id(TENANT_A)
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    assert schedule.action.id
    assert schedule.action.task_queue == "compliance-queue"
    assert schedule.action.args == [{"tenant_id": str(TENANT_A)}]
    assert schedule.spec.cron_expressions == ["30 0 * * *"]
    assert schedule.spec.time_zone_name == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_suspended_tenant_is_skipped(mock_db, mock_temporal):
    from workflows.compliance import ensure_statutory_compliance_schedules, _statutory_schedule_id

    await ensure_statutory_compliance_schedules(
        db=mock_db, temporal_client=mock_temporal, cron_expression="30 0 * * *",
    )

    created_ids = [call.args[0] for call in mock_temporal.create_schedule.await_args_list]
    assert _statutory_schedule_id(TENANT_B) not in created_ids


@pytest.mark.asyncio
async def test_ensure_one_tenant_schedule_updates_existing_cron():
    import dataclasses
    from temporalio.client import (
        Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleUpdateInput, ScheduleUpdate,
    )
    from workflows.compliance import StatutoryComplianceWorkflow, ensure_one_tenant_statutory_schedule

    existing = Schedule(
        action=ScheduleActionStartWorkflow(StatutoryComplianceWorkflow.run, id="x", task_queue="compliance-queue"),
        spec=ScheduleSpec(cron_expressions=["0 0 * * *"]),
    )
    captured = {}

    async def fake_update(updater, **kw):
        desc = MagicMock()
        desc.schedule = existing
        captured["result"] = await updater(ScheduleUpdateInput(description=desc))

    handle = MagicMock()
    handle.describe = AsyncMock(return_value=None)
    handle.update = fake_update
    client = MagicMock()
    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()

    await ensure_one_tenant_statutory_schedule(client, tenant_id=str(TENANT_A), cron_expression="30 0 * * *")

    client.create_schedule.assert_not_awaited()
    result = captured["result"]
    assert isinstance(result, ScheduleUpdate)
    assert result.schedule.spec.cron_expressions == ["30 0 * * *"]


def test_statutory_schedule_id_is_deterministic():
    from workflows.compliance import _statutory_schedule_id

    assert _statutory_schedule_id(TENANT_A) == f"statutory-compliance-{TENANT_A}"


@pytest.mark.asyncio
async def test_ensure_statutory_compliance_schedules_query_filters_active():
    from workflows.compliance import ensure_statutory_compliance_schedules

    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    tc = MagicMock()

    await ensure_statutory_compliance_schedules(db=db, temporal_client=tc, cron_expression="30 0 * * *")

    db.fetch.assert_awaited_once()
    sql = db.fetch.await_args.args[0].lower()
    assert "status" in sql
    assert db.fetch.await_args.args[1] == "ACTIVE", \
        "must filter on the parameterized status value, not string-interpolate it into the SQL"
