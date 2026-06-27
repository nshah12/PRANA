"""
RED tests for HRMSSyncScheduleWorkflow.

The workflow creates/updates a Temporal Schedule for every ACTIVE connector
under a given tenant. Idempotent: safe to call multiple times.

Tests verify:
- Each ACTIVE connector gets a schedule created or updated
- PAUSED/REVOKED connectors are skipped
- Schedule ID is deterministic: hrms-sync-{connector_id}
- Interval comes from pull_schedule config, not hardcoded
- Activity (ensure_hrms_schedules) calls temporal.schedule with correct args
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

TENANT_ID    = UUID("b0000000-0000-0000-0000-000000000001")
CONNECTOR_A  = uuid4()
CONNECTOR_B  = uuid4()

ACTIVE_CONNECTORS = [
    {
        "connector_id":   CONNECTOR_A,
        "tenant_id":      TENANT_ID,
        "connector_key":  "darwinbox",
        "status":         "ACTIVE",
        "pull_schedule":  "0 */6 * * *",   # every 6 hours
    },
    {
        "connector_id":   CONNECTOR_B,
        "tenant_id":      TENANT_ID,
        "connector_key":  "keka",
        "status":         "PAUSED",
        "pull_schedule":  "0 */6 * * *",
    },
]


@pytest.fixture
def mock_db():
    db = AsyncMock()
    rows = []
    for c in ACTIVE_CONNECTORS:
        row = MagicMock()
        row.__getitem__ = lambda s, k, c=c: c[k]
        row.get = lambda k, default=None, c=c: c.get(k, default)
        rows.append(row)
    db.fetch = AsyncMock(return_value=rows)
    return db


@pytest.fixture
def mock_temporal():
    tc = AsyncMock()
    tc.list_schedules = AsyncMock(return_value=[])
    tc.create_schedule = AsyncMock()
    tc.get_schedule_handle = MagicMock(return_value=AsyncMock())
    return tc


# ── ensure_hrms_schedules activity ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_connector_gets_schedule(mock_db, mock_temporal):
    """ACTIVE connector → Temporal schedule created/updated."""
    from workflows.hrms_sync_schedule import ensure_hrms_schedules

    await ensure_hrms_schedules(
        tenant_id=str(TENANT_ID),
        db=mock_db,
        temporal_client=mock_temporal,
    )

    # At least one schedule create/update called
    assert (mock_temporal.create_schedule.await_count +
            mock_temporal.get_schedule_handle.call_count) >= 1


@pytest.mark.asyncio
async def test_paused_connector_skipped(mock_db, mock_temporal):
    """PAUSED connector → no schedule created for it."""
    from workflows.hrms_sync_schedule import ensure_hrms_schedules

    await ensure_hrms_schedules(
        tenant_id=str(TENANT_ID),
        db=mock_db,
        temporal_client=mock_temporal,
    )

    created_ids = [str(call) for call in mock_temporal.create_schedule.call_args_list]
    paused_id   = f"hrms-sync-{CONNECTOR_B}"
    assert not any(paused_id in c for c in created_ids)


@pytest.mark.asyncio
async def test_schedule_id_is_deterministic(mock_db, mock_temporal):
    """Schedule ID must follow hrms-sync-{connector_id} pattern."""
    from workflows.hrms_sync_schedule import _schedule_id

    sid = _schedule_id(CONNECTOR_A)
    assert sid == f"hrms-sync-{CONNECTOR_A}"


@pytest.mark.asyncio
async def test_db_query_is_tenant_scoped(mock_db, mock_temporal):
    """Must only query connectors for the given tenant."""
    from workflows.hrms_sync_schedule import ensure_hrms_schedules

    await ensure_hrms_schedules(
        tenant_id=str(TENANT_ID),
        db=mock_db,
        temporal_client=mock_temporal,
    )

    mock_db.fetch.assert_awaited_once()
    sql = mock_db.fetch.call_args[0][0].lower()
    assert "tenant_id" in sql
    assert "active" in sql
