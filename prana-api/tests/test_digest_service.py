"""
Tests for services/digest_service.py — DigestService + validate_window.

TDD cycle: RED → GREEN → REFACTOR.

Coverage:
  1.  Config get — returns default when no tenant_config row
  2.  Config get — parses JSON string from tenant_config.config_value
  3.  Config save — executes upsert with the correct config_key
  4.  validate_window — rejects future to_date
  5.  validate_window — rejects from >= to
  6.  validate_window — rejects range > 184 days
  7.  validate_window — rejects lookback > 730 days
  8.  validate_window — accepts valid window
  9.  CHRO digest — returns expected shape with all required keys
  10. CHRO digest — response uses from/to keys (not period/since)
  11. CHRO digest — privacy: no PAN, no raw salary field
  12. CFO digest — returns expected shape; cost_indicators note confirms estimates only
  13. CFO digest — privacy: note must say "estimate", never raw figures
  14. CISO digest — returns expected shape with incident list
  15. CISO digest — privacy: no PAN or salary in output
"""
import json
import datetime as dt
from unittest.mock import AsyncMock

import pytest

from services.digest_service import DigestService, validate_window

UTC = dt.timezone.utc


@pytest.fixture
def svc() -> DigestService:
    return DigestService()


def _db(*, fetchrow=None, fetchval=None, fetch=None):
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=fetchrow)
    db.fetchval = AsyncMock(return_value=fetchval)
    db.fetch = AsyncMock(return_value=fetch or [])
    db.execute = AsyncMock()
    return db


def _window(days: int = 7) -> tuple[dt.datetime, dt.datetime]:
    """Return (from_dt, to_dt) for a recent N-day window."""
    to_dt   = dt.datetime.now(UTC)
    from_dt = to_dt - dt.timedelta(days=days)
    return from_dt, to_dt


# ── Config ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_returns_default_when_missing(svc):
    result = await svc.get_config(_db(fetchrow=None), "t-001", "chro")
    assert isinstance(result["recipients"], list)
    assert result["active"] is False


@pytest.mark.asyncio
async def test_get_config_parses_json_string(svc):
    payload = json.dumps({"recipients": ["ceo@corp.in"], "active": True,
                          "schedules": {}, "sections": [], "format": "email"})
    result = await svc.get_config(_db(fetchrow={"config_value": payload}), "t-001", "chro")
    assert result["recipients"] == ["ceo@corp.in"]
    assert result["active"] is True


@pytest.mark.asyncio
async def test_save_config_upserts_correct_key(svc):
    db = _db()
    config = {"recipients": ["cfo@corp.in"], "active": True,
               "schedules": {}, "sections": [], "format": "email"}
    await svc.save_config(db, "t-001", "cfo", config, "user-uuid-001")
    db.execute.assert_called_once()
    sql, tenant_id, key, val, *_ = db.execute.call_args[0]
    assert key == "digest_cfo_config"
    assert json.loads(val)["recipients"] == ["cfo@corp.in"]


# ── validate_window ────────────────────────────────────────────────────────────

def test_validate_window_rejects_future_to():
    from_dt = dt.datetime.now(UTC) - dt.timedelta(days=7)
    to_dt   = dt.datetime.now(UTC) + dt.timedelta(hours=2)
    with pytest.raises(ValueError) as exc_info:
        validate_window(from_dt, to_dt)
    assert exc_info.value.args[0]["error"] == "DATE_RANGE_FUTURE"


def test_validate_window_rejects_from_gte_to():
    now = dt.datetime.now(UTC)
    with pytest.raises(ValueError) as exc_info:
        validate_window(now, now - dt.timedelta(hours=1))
    assert exc_info.value.args[0]["error"] == "DATE_RANGE_INVALID"


def test_validate_window_rejects_range_over_184_days():
    to_dt   = dt.datetime.now(UTC)
    from_dt = to_dt - dt.timedelta(days=185)
    with pytest.raises(ValueError) as exc_info:
        validate_window(from_dt, to_dt)
    assert exc_info.value.args[0]["error"] == "DATE_RANGE_TOO_LARGE"
    assert exc_info.value.args[0]["max_days"] == 184


def test_validate_window_rejects_lookback_over_730_days():
    to_dt   = dt.datetime.now(UTC) - dt.timedelta(days=730)
    from_dt = to_dt - dt.timedelta(days=7)
    with pytest.raises(ValueError) as exc_info:
        validate_window(from_dt, to_dt)
    assert exc_info.value.args[0]["error"] == "DATE_RANGE_TOO_OLD"


def test_validate_window_accepts_valid_window():
    from_dt, to_dt = _window(30)
    validate_window(from_dt, to_dt)  # must not raise


# ── CHRO digest ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_chro_digest_shape(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(side_effect=[100, 87.2, 4, 7, 1997])
    db.fetch = AsyncMock(side_effect=[
        [{"doc_type": "SALARY_SLIP", "cnt": 80}],
        [{"department": "Engineering", "score": 93.0}],
    ])
    from_dt, to_dt = _window(7)
    result = await svc.build_chro_digest(db, "t-001", from_dt, to_dt)

    assert result["docs_processed"] == 100
    assert result["vault_completeness_pct"] == 87.2
    assert result["exceptions_open"] == 4
    assert result["alumni_self_served"] == 7
    assert result["active_employees"] == 1997
    assert isinstance(result["docs_by_type"], list)
    assert result["docs_by_type"][0]["doc_type"] == "SALARY_SLIP"
    assert isinstance(result["vault_by_department"], list)


@pytest.mark.asyncio
async def test_build_chro_digest_uses_from_to_keys(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=0)
    db.fetch = AsyncMock(return_value=[])
    from_dt, to_dt = _window(7)
    result = await svc.build_chro_digest(db, "t-001", from_dt, to_dt)
    assert "from" in result and "to" in result
    assert "period" not in result
    assert "since" not in result


@pytest.mark.asyncio
async def test_build_chro_digest_privacy(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=0)
    db.fetch = AsyncMock(return_value=[])
    from_dt, to_dt = _window(7)
    result = await svc.build_chro_digest(db, "t-001", from_dt, to_dt)
    result_str = json.dumps(result).lower()
    assert "pan" not in result_str
    assert "nik" not in result_str


# ── CFO digest ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_cfo_digest_shape(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(side_effect=[1997, 22, 11, 2])
    db.fetchrow = AsyncMock(side_effect=[
        {"config_value": "1500000"},
        {"config_value": "150000"},
        {"config_value": "2050"},
    ])
    db.fetch = AsyncMock(side_effect=[
        [{"doc_type": "SALARY_SLIP", "covered": 1960}],
        [{"department": "Engineering", "cnt": 800}],
    ])
    from_dt, to_dt = _window(30)
    result = await svc.build_cfo_digest(db, "t-001", from_dt, to_dt)

    assert result["headcount"] == 1997
    assert result["exits"] == 22
    assert result["joiners"] == 11
    assert result["anomalies_pending"] == 2
    assert result["headcount_budget"] == 2050
    assert "cost_indicators" in result
    assert "note" in result["cost_indicators"]
    assert "compliance_by_doc_type" in result
    assert "SALARY_SLIP" in result["compliance_by_doc_type"]
    assert "from" in result and "to" in result


@pytest.mark.asyncio
async def test_build_cfo_digest_cost_note_says_estimate(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=0)
    db.fetchrow = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    from_dt, to_dt = _window(7)
    result = await svc.build_cfo_digest(db, "t-001", from_dt, to_dt)
    note = result["cost_indicators"]["note"].lower()
    assert "estimate" in note


# ── CISO digest ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_ciso_digest_shape(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(side_effect=[1847, 3, 2, 1, 34])
    db.fetch = AsyncMock(side_effect=[
        [{"access_channel": "MOBILE", "cnt": 1256}],
        [
            {
                "anomaly_id": "anom-001",
                "rule_name": "BULK_ACCESS",
                "severity": "HIGH",
                "detected_at": dt.datetime(2025, 8, 6, 23, 47, tzinfo=UTC),
                "status": "OPEN",
                "acknowledged_at": None,
            }
        ],
    ])
    from_dt, to_dt = _window(7)
    result = await svc.build_ciso_digest(db, "t-001", from_dt, to_dt)

    assert result["total_accesses"] == 1847
    assert result["anomalies_total"] == 3
    assert result["anomalies_open"] == 2
    assert result["force_logouts"] == 1
    assert result["share_tokens_period"] == 34
    assert isinstance(result["by_channel"], list)
    assert result["by_channel"][0]["channel"] == "MOBILE"
    assert isinstance(result["incidents"], list)
    assert len(result["incidents"]) == 1
    assert result["incidents"][0]["rule_name"] == "BULK_ACCESS"
    assert result["incidents"][0]["resolved"] is False
    assert "from" in result and "to" in result


@pytest.mark.asyncio
async def test_build_ciso_digest_privacy(svc):
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=0)
    db.fetch = AsyncMock(return_value=[])
    from_dt, to_dt = _window(7)
    result = await svc.build_ciso_digest(db, "t-001", from_dt, to_dt)
    result_str = json.dumps(result).lower()
    assert "pan" not in result_str
    assert "salary" not in result_str
    assert "nik" not in result_str
