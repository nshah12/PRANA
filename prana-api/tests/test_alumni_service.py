"""
Tests for alumni network: consent, CHRO list, outreach send, rate limit.
TDD cycle: these tests drive the AlumniService and alumni router.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta

from services.alumni_service import AlumniService, _tenure_band, _time_since_exit


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_db(**overrides):
    db = AsyncMock()
    db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    for k, v in overrides.items():
        setattr(db, k, AsyncMock(return_value=v))
    return db

def _make_svc(db, kafka=None):
    return AlumniService(db=db, kafka=kafka, config={"outreach_max_per_month": 3})


# ── Unit: consent ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_alumni_consent_grant():
    db = _make_db()
    svc = _make_svc(db)
    result = await svc.set_alumni_consent("emp-1", grant=True)
    assert result["alumni_visibility_consent"] is True
    db.execute.assert_called()
    # Confirm the UPSERT touched employee_consent
    call_sql = db.execute.call_args_list[0][0][0]
    assert "alumni_visibility" in call_sql
    assert "is_active" in call_sql

@pytest.mark.asyncio
async def test_set_alumni_consent_withdraw_marks_outreach_ignored():
    db = _make_db()
    svc = _make_svc(db)
    await svc.set_alumni_consent("emp-1", grant=False)
    # Second execute call: UPDATE alumni_outreach SET status = 'OPTED_OUT'
    calls = [c[0][0] for c in db.execute.call_args_list]
    assert any("OPTED_OUT" in sql for sql in calls)

@pytest.mark.asyncio
async def test_get_alumni_consent_not_set():
    db = _make_db(fetchrow=None)
    svc = _make_svc(db)
    result = await svc.get_alumni_consent("emp-new")
    assert result["alumni_visibility_consent"] is False


# ── Unit: CHRO list ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alumni_returns_items():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "employee_uuid":         "uuid-1",
        "designation":           "Senior Engineer",
        "department":            "Engineering",
        "location":              "Bengaluru",
        "grade":                 "L5",
        "doj":                   date(2019, 1, 1),
        "dol":                   date(2023, 6, 1),
        "last_outreach_status":  None,
        "last_outreach_at":      None,
    }[k]
    db = _make_db(fetch=[row], fetchval=1)
    svc = _make_svc(db)
    result = await svc.list_alumni("tenant-1")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["designation"] == "Senior Engineer"
    assert item["tenure_band"] == "4–7 years"
    # Name must NOT appear in CHRO list view
    assert "full_name" not in item

@pytest.mark.asyncio
async def test_list_alumni_excludes_recent_exits():
    """MIN_EXIT_DAYS (30) passed as $2 to the parameterized query — not interpolated."""
    db = _make_db(fetch=[], fetchval=0)
    svc = _make_svc(db)
    await svc.list_alumni("tenant-1")
    call_args = db.fetch.call_args[0]
    # arg 0 = SQL, arg 1 = tenant_id ($1), arg 2 = _MIN_EXIT_DAYS ($2)
    assert call_args[2] == 30


# ── Unit: outreach ────────────────────────────────────────────────────────────

def _alumni_row(consent_active=True, dol=None):
    r = MagicMock()
    dol = dol or (date.today() - timedelta(days=60))
    r.__getitem__ = lambda self, k: {
        "employee_user_id": "user-1",
        "full_name":        "Priya Sharma",
        "dol":              dol,
        "consent_active":   consent_active,
    }[k]
    return r

@pytest.mark.asyncio
async def test_send_outreach_success():
    db = _make_db(fetchrow=_alumni_row(), fetchval=0)
    db.fetchval = AsyncMock(side_effect=["user-1-outreach-id", 0])
    kafka = AsyncMock()
    svc = _make_svc(db, kafka)
    result = await svc.send_outreach(
        tenant_id="t-1", oa_user_id="oa-1",
        employee_uuid="emp-uuid-1",
        subject="We'd love to reconnect", body_text="Hi Priya, would you consider rejoining?",
    )
    assert result.get("error") is None
    kafka.notify_bell.assert_called_once()
    kafka.notify_email.assert_called_once()

@pytest.mark.asyncio
async def test_send_outreach_no_consent():
    db = _make_db(fetchrow=_alumni_row(consent_active=False))
    svc = _make_svc(db)
    result = await svc.send_outreach(
        "t-1", "oa-1", "emp-1", "Subject", "Body text here."
    )
    assert result["error"] == "ALUMNI_NO_CONSENT"

@pytest.mark.asyncio
async def test_send_outreach_rate_limit():
    db = _make_db(fetchrow=_alumni_row())
    # fetchval called for outreach_id AND recent_count — recent_count = 3 (at limit)
    db.fetchval = AsyncMock(side_effect=[3])
    svc = _make_svc(db)
    result = await svc.send_outreach(
        "t-1", "oa-1", "emp-1", "Subject", "Body text here."
    )
    assert result["error"] == "OUTREACH_RATE_LIMIT"
    assert result["limit"] == 3

@pytest.mark.asyncio
async def test_send_outreach_still_active_employee():
    """Employee who exited < 30 days ago cannot be contacted."""
    recent_dol = date.today() - timedelta(days=10)
    db = _make_db(fetchrow=_alumni_row(dol=recent_dol))
    svc = _make_svc(db)
    result = await svc.send_outreach(
        "t-1", "oa-1", "emp-1", "Subject", "Body text here."
    )
    assert result["error"] == "EMPLOYEE_STILL_ACTIVE"


# ── Unit: router auth gates ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_router_consent_requires_auth(client):
    response = await client.post("/v1/alumni/consent", json={"grant": True})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_router_chro_list_requires_oa_role(client):
    response = await client.get("/v1/alumni/org/list")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_router_outreach_requires_oa_role(client):
    response = await client.post("/v1/alumni/org/outreach", json={
        "employee_uuid": "x", "subject": "Hello", "body_text": "Hi there!"
    })
    assert response.status_code == 401


# ── Unit: helpers ─────────────────────────────────────────────────────────────

def test_tenure_band():
    assert _tenure_band(date(2020, 1, 1), date(2020, 6, 1))  == "< 1 year"
    assert _tenure_band(date(2020, 1, 1), date(2021, 6, 1))  == "1–2 years"
    assert _tenure_band(date(2018, 1, 1), date(2021, 6, 1))  == "2–4 years"
    assert _tenure_band(date(2016, 1, 1), date(2021, 6, 1))  == "4–7 years"
    assert _tenure_band(date(2010, 1, 1), date(2021, 6, 1))  == "7+ years"

def test_time_since_exit():
    today = date.today()
    assert "month" in _time_since_exit(today - timedelta(days=45))
    assert "year"  in _time_since_exit(today - timedelta(days=400))
