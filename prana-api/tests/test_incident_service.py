"""
Tests for services/incident_service.py

TDD order:
  RED  — tests fail until incident_service.py exists
  GREEN — implement to pass
  REFACTOR — clean up

Covers:
  - create_incident() writes incident row with correct severity / SLA deadline
  - P0 SLA = 30 min, P1 = 4 hr, P2 = 24 hr
  - auto_create_for_anomaly() creates incident for P0/P1, not P2/P3
  - resolve_incident() sets resolved_at + resolved_by + resolution_note
  - escalate_incident() sets escalated_at + status=ESCALATED
  - get_incidents() for CISO filtered by tenant, for PA unfiltered
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.incident_service import IncidentService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)
    db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    return db


@pytest.fixture
def svc(mock_db):
    return IncidentService(db=mock_db)


# ---------------------------------------------------------------------------
# 1. create_incident()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_incident_writes_row(svc, mock_db):
    """create_incident() must INSERT into incident table."""
    mock_db.fetchval.return_value = "inc-uuid-001"
    await svc.create_incident(
        incident_type="SECURITY_ANOMALY",
        severity="P1",
        title="Bulk document access detected",
        tenant_id="tenant-001",
        source_table="anomaly_event",
        source_id="anom-uuid-001",
        assigned_role="CISO",
    )
    mock_db.execute.assert_called_once()
    sql = mock_db.execute.call_args[0][0]
    assert "incident" in sql.lower()
    assert "INSERT" in sql.upper()


@pytest.mark.asyncio
async def test_create_incident_p0_sla_30_min(svc, mock_db):
    """P0 incident SLA deadline must be NOW + 30 minutes."""
    before = datetime.now(timezone.utc)
    await svc.create_incident(
        incident_type="SECURITY_ANOMALY",
        severity="P0",
        title="Critical anomaly",
        tenant_id="tenant-001",
    )
    # Verify the SLA arg passed is within 31 min from now
    sql, *args = mock_db.execute.call_args[0]
    sla_arg = next((a for a in args if isinstance(a, datetime)), None)
    assert sla_arg is not None, "SLA deadline (datetime) not passed to DB execute"
    delta = sla_arg - before
    assert timedelta(minutes=29) <= delta <= timedelta(minutes=31), (
        f"P0 SLA should be ~30min, got {delta}"
    )


@pytest.mark.asyncio
async def test_create_incident_p1_sla_4_hr(svc, mock_db):
    """P1 incident SLA deadline must be NOW + 4 hours."""
    before = datetime.now(timezone.utc)
    await svc.create_incident(
        incident_type="SECURITY_ANOMALY",
        severity="P1",
        title="P1 anomaly",
        tenant_id="tenant-001",
    )
    sql, *args = mock_db.execute.call_args[0]
    sla_arg = next((a for a in args if isinstance(a, datetime)), None)
    assert sla_arg is not None
    delta = sla_arg - before
    assert timedelta(hours=3, minutes=59) <= delta <= timedelta(hours=4, minutes=1)


@pytest.mark.asyncio
async def test_create_incident_p2_sla_24_hr(svc, mock_db):
    """P2 incident SLA deadline must be NOW + 24 hours."""
    before = datetime.now(timezone.utc)
    await svc.create_incident(
        incident_type="SLA_BREACH",
        severity="P2",
        title="Exception SLA breached",
        tenant_id="tenant-001",
    )
    sql, *args = mock_db.execute.call_args[0]
    sla_arg = next((a for a in args if isinstance(a, datetime)), None)
    assert sla_arg is not None
    delta = sla_arg - before
    assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1)


# ---------------------------------------------------------------------------
# 2. auto_create_for_anomaly()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_create_for_p0_anomaly(svc, mock_db):
    """P0 anomaly must auto-create an incident."""
    result = await svc.auto_create_for_anomaly(
        anomaly_id="anom-uuid-001",
        tenant_id="tenant-001",
        rule_name="BULK_ACCESS",
        severity="P0",
        assigned_ciso_id="ciso-uuid-001",
    )
    assert result is not None
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_auto_create_for_p1_anomaly(svc, mock_db):
    """P1 anomaly must auto-create an incident."""
    result = await svc.auto_create_for_anomaly(
        anomaly_id="anom-uuid-002",
        tenant_id="tenant-001",
        rule_name="FOREIGN_IP_LOGIN",
        severity="P1",
        assigned_ciso_id="ciso-uuid-001",
    )
    assert result is not None
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_no_auto_create_for_p2_anomaly(svc, mock_db):
    """P2 anomaly must NOT auto-create an incident."""
    result = await svc.auto_create_for_anomaly(
        anomaly_id="anom-uuid-003",
        tenant_id="tenant-001",
        rule_name="SLOW_DRAIN",
        severity="P2",
        assigned_ciso_id="ciso-uuid-001",
    )
    assert result is None
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_no_auto_create_for_p3_anomaly(svc, mock_db):
    """P3 anomaly must NOT auto-create an incident."""
    result = await svc.auto_create_for_anomaly(
        anomaly_id="anom-uuid-004",
        tenant_id="tenant-001",
        rule_name="LOW_SIGNAL",
        severity="P3",
        assigned_ciso_id="ciso-uuid-001",
    )
    assert result is None
    mock_db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# 3. resolve_incident()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_incident_happy_path(svc, mock_db):
    """resolve_incident() must UPDATE incident row with resolved_at and status=RESOLVED."""
    mock_db.fetchrow.return_value = {
        "incident_id": "inc-uuid-001",
        "tenant_id": "tenant-001",
        "status": "OPEN",
    }
    await svc.resolve_incident(
        incident_id="inc-uuid-001",
        resolved_by="ciso-uuid-001",
        resolution_note="Investigated — false positive due to batch export job",
        tenant_id="tenant-001",
    )
    mock_db.execute.assert_called_once()
    sql = mock_db.execute.call_args[0][0]
    assert "RESOLVED" in sql
    assert "resolved_at" in sql.lower()


@pytest.mark.asyncio
async def test_resolve_incident_not_found_raises(svc, mock_db):
    """resolve_incident() must raise ValueError if incident not found."""
    mock_db.fetchrow.return_value = None
    with pytest.raises(ValueError, match="not found"):
        await svc.resolve_incident(
            incident_id="does-not-exist",
            resolved_by="ciso-uuid-001",
            resolution_note="test",
            tenant_id="tenant-001",
        )


@pytest.mark.asyncio
async def test_resolve_incident_cross_tenant_blocked(svc, mock_db):
    """resolve_incident() must reject if incident belongs to different tenant."""
    mock_db.fetchrow.return_value = {
        "incident_id": "inc-uuid-001",
        "tenant_id": "tenant-OTHER",
        "status": "OPEN",
    }
    with pytest.raises(ValueError, match="not found"):
        await svc.resolve_incident(
            incident_id="inc-uuid-001",
            resolved_by="ciso-uuid-001",
            resolution_note="test",
            tenant_id="tenant-001",  # different from row's tenant
        )


# ---------------------------------------------------------------------------
# 4. escalate_incident()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_incident_sets_escalated_at(svc, mock_db):
    """escalate_incident() must set escalated_at and status=ESCALATED."""
    mock_db.fetchrow.return_value = {
        "incident_id": "inc-uuid-001",
        "tenant_id": "tenant-001",
        "status": "OPEN",
    }
    await svc.escalate_incident(incident_id="inc-uuid-001", tenant_id="tenant-001")
    sql = mock_db.execute.call_args[0][0]
    assert "ESCALATED" in sql


# ---------------------------------------------------------------------------
# 5. get_incidents() — tenant-scoped for CISO, unscoped for PA
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_incidents_ciso_scoped_to_tenant(svc, mock_db):
    """CISO incident list must always include tenant_id in the query."""
    await svc.get_incidents(tenant_id="tenant-001", severity=None, status=None)
    sql, *args = mock_db.fetch.call_args[0]
    assert "tenant-001" in args


@pytest.mark.asyncio
async def test_get_incidents_pa_no_tenant_filter(svc, mock_db):
    """PA incident list with tenant_id=None must NOT filter by tenant."""
    await svc.get_incidents(tenant_id=None, severity=None, status=None)
    sql, *args = mock_db.fetch.call_args[0]
    # tenant_id=None means cross-tenant view — the literal "tenant-" should not appear in args
    assert not any(isinstance(a, str) and a.startswith("tenant-") for a in args)


@pytest.mark.asyncio
async def test_get_incidents_filter_by_severity(svc, mock_db):
    """Severity filter must be included in the query."""
    await svc.get_incidents(tenant_id="tenant-001", severity="P0", status=None)
    sql, *args = mock_db.fetch.call_args[0]
    assert "P0" in args
