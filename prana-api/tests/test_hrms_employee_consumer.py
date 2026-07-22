"""
RED tests for HRMS_EMPLOYEE_SYNCED handler in EmployeeConsumer.

Tests verify:
- New employee (not in employee_master) → INSERT + publish EMPLOYEE_ONBOARDED
- Existing employee (already in employee_master) → UPDATE designation/department/location/status
- Missing tenant_id or employee_id → logged and skipped, no crash
- Offboarded employee (status=inactive) → set dol, start EmployeeExitWorkflow
- Privacy: no salary fields stored or logged
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

TENANT_ID       = UUID("b0000000-0000-0000-0000-000000000001")
EMPLOYEE_UUID   = UUID("a0000000-0000-0000-0000-000000000001")
EMP_ID_ORG      = "EMP001"

HRMS_SYNCED_EVENT = {
    "event_type":   "HRMS_EMPLOYEE_SYNCED",
    "tenant_id":    str(TENANT_ID),
    "connector_id": str(uuid4()),
    "employee_data": {
        "employee_id":  EMP_ID_ORG,
        "first_name":   "Rahul",
        "last_name":    "Sharma",
        "date_of_join": "2022-01-15",
        "designation":  "Software Engineer",
        "department":   "Engineering",
        "location":     "Bangalore",
        "status":       "active",
    },
}

EXISTING_ROW = {
    "employee_uuid":   EMPLOYEE_UUID,
    "employee_user_id": uuid4(),
    "designation":     "Junior Software Engineer",
    "department":      "Engineering",
    "status":          "ACTIVE",
    "dol":             None,
}


@pytest.fixture
def consumer():
    from kafka.consumers.employee_consumer import EmployeeConsumer
    from config import Settings
    settings = Settings(
        app_env="test",
        debug=True,
        db_host="localhost",
        db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/15",
        sms_provider="dev",
    )
    mock_pool   = MagicMock()
    mock_temp   = AsyncMock()
    mock_kafka  = AsyncMock()
    mock_kafka.employee_event = AsyncMock()
    c = EmployeeConsumer(settings=settings, db_pool=mock_pool,
                         temporal_client=mock_temp, kafka_producer=mock_kafka)
    return c


@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch    = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute  = AsyncMock()
    return conn


# ── New employee ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_employee_insert_called(consumer, mock_conn):
    """HRMS_EMPLOYEE_SYNCED for unknown emp_id_org → INSERT employee_master."""
    mock_conn.fetchrow.return_value = None  # not found
    mock_conn.fetchval.return_value = EMPLOYEE_UUID

    await consumer._handle_hrms_employee_synced(HRMS_SYNCED_EVENT, mock_conn)

    # fetchrow to look up existing, then fetchval for INSERT
    assert mock_conn.fetchrow.await_count >= 1
    assert mock_conn.fetchval.await_count >= 1


@pytest.mark.asyncio
async def test_new_employee_triggers_onboarding_event(consumer, mock_conn):
    """New employee → publish EMPLOYEE_ONBOARDED so workflow can start."""
    mock_conn.fetchrow.return_value = None
    mock_conn.fetchval.return_value = EMPLOYEE_UUID

    await consumer._handle_hrms_employee_synced(HRMS_SYNCED_EVENT, mock_conn)

    consumer._kafka.employee_event.assert_awaited_once()
    call_event = consumer._kafka.employee_event.call_args[0][0]
    assert call_event["event_type"] == "EMPLOYEE_ONBOARDED"
    assert call_event["tenant_id"]  == str(TENANT_ID)


# ── Existing employee ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_existing_employee_update_called(consumer, mock_conn):
    """HRMS_EMPLOYEE_SYNCED for known emp_id_org → UPDATE, not INSERT."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: EXISTING_ROW[k]
    mock_conn.fetchrow.return_value = row

    await consumer._handle_hrms_employee_synced(HRMS_SYNCED_EVENT, mock_conn)

    mock_conn.execute.assert_awaited()
    call_sql = mock_conn.execute.call_args[0][0].lower()
    assert "update" in call_sql
    assert "employee_master" in call_sql


@pytest.mark.asyncio
async def test_existing_employee_no_insert(consumer, mock_conn):
    """Existing employee must not trigger a second INSERT."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: EXISTING_ROW[k]
    mock_conn.fetchrow.return_value = row

    await consumer._handle_hrms_employee_synced(HRMS_SYNCED_EVENT, mock_conn)

    # fetchval is used only for INSERT RETURNING — should not be called for update
    for call in mock_conn.fetchval.call_args_list:
        sql = str(call).lower()
        assert "insert" not in sql


# ── Offboarded employee ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_offboarded_employee_sets_dol(consumer, mock_conn):
    """Status=inactive/offboarded → set dol, start EmployeeExitWorkflow."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: EXISTING_ROW[k]
    mock_conn.fetchrow.return_value = row

    exit_event = {
        **HRMS_SYNCED_EVENT,
        "employee_data": {
            **HRMS_SYNCED_EVENT["employee_data"],
            "status": "inactive",
        },
    }
    await consumer._handle_hrms_employee_synced(exit_event, mock_conn)

    mock_conn.execute.assert_awaited()
    call_sql = mock_conn.execute.call_args[0][0].lower()
    assert "dol" in call_sql


# ── Validation ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_employee_id_skipped(consumer, mock_conn):
    """Event with no employee_id in employee_data → skip, no DB call."""
    bad_event = {
        **HRMS_SYNCED_EVENT,
        "employee_data": {"first_name": "Rahul"},  # no employee_id
    }
    await consumer._handle_hrms_employee_synced(bad_event, mock_conn)

    mock_conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_tenant_id_skipped(consumer, mock_conn):
    """Event with no tenant_id → skip, no DB call."""
    bad_event = {**HRMS_SYNCED_EVENT, "tenant_id": None}
    await consumer._handle_hrms_employee_synced(bad_event, mock_conn)

    mock_conn.fetchrow.assert_not_awaited()


# ── Privacy ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_salary_written_to_db(consumer, mock_conn):
    """Privacy: no CTC or salary field must appear in any DB call."""
    salary_event = {
        **HRMS_SYNCED_EVENT,
        "employee_data": {
            **HRMS_SYNCED_EVENT["employee_data"],
            "ctc": "1200000",
            "salary": "100000",
        },
    }
    mock_conn.fetchrow.return_value = None
    mock_conn.fetchval.return_value = EMPLOYEE_UUID

    await consumer._handle_hrms_employee_synced(salary_event, mock_conn)

    for call in mock_conn.fetchval.call_args_list + mock_conn.execute.call_args_list:
        assert "1200000" not in str(call)
        assert "salary"  not in str(call).lower()
