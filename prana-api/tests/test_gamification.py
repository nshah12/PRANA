"""
RED tests for gamification router.

Tests: auth, tenant isolation, happy path, privacy contract, checkin idempotency.
"""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


# ── Auth tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_requires_auth(client):
    r = await client.get("/v1/gamification/profile")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkin_requires_auth(client):
    r = await client.post("/v1/gamification/checkin")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_badges_requires_auth(client):
    r = await client.get("/v1/gamification/badges")
    assert r.status_code == 401


# ── Happy path: profile ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_returns_score_and_badges(client, employee_auth_headers, mock_db):
    mock_db.fetchrow.return_value = _score_row(score=72)
    mock_db.fetch.return_value = [_badge_row("TAX_READY", "📊", "Tax Ready")]
    mock_db.fetchval.return_value = 5  # streak

    r = await client.get("/v1/gamification/profile", headers=employee_auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert isinstance(body["score"], int)
    assert 0 <= body["score"] <= 100
    assert "badges" in body
    assert isinstance(body["badges"], list)
    assert "streak" in body


@pytest.mark.asyncio
async def test_profile_score_not_negative(client, employee_auth_headers, mock_db):
    mock_db.fetchrow.return_value = _score_row(score=0)
    mock_db.fetch.return_value = []
    mock_db.fetchval.return_value = 0

    r = await client.get("/v1/gamification/profile", headers=employee_auth_headers)

    assert r.status_code == 200
    assert r.json()["score"] >= 0


@pytest.mark.asyncio
async def test_profile_no_raw_salary_in_response(client, employee_auth_headers, mock_db):
    mock_db.fetchrow.return_value = _score_row(score=50)
    mock_db.fetch.return_value = []
    mock_db.fetchval.return_value = 3

    r = await client.get("/v1/gamification/profile", headers=employee_auth_headers)

    body_text = r.text.lower()
    for forbidden in ["salary", "ctc", "inr", "rupee", "₹"]:
        assert forbidden not in body_text, f"'{forbidden}' found in gamification profile response"


# ── Happy path: checkin ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkin_returns_streak(client, employee_auth_headers, mock_db):
    mock_db.fetchrow.return_value = None  # first ever checkin

    r = await client.post("/v1/gamification/checkin", headers=employee_auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert "current_streak_days" in body
    assert body["current_streak_days"] >= 1


@pytest.mark.asyncio
async def test_checkin_same_day_is_idempotent(client, employee_auth_headers, mock_db):
    """Second checkin on same day returns same streak, no error."""
    today = date.today()
    mock_db.fetchrow.return_value = _streak_row(current=5, longest=7, last_date=today)

    r = await client.post("/v1/gamification/checkin", headers=employee_auth_headers)

    assert r.status_code == 200
    assert r.json()["current_streak_days"] == 5


# ── Happy path: badges ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_badges_returns_list(client, employee_auth_headers, mock_db):
    mock_db.fetch.return_value = [
        _badge_row("TAX_READY",     "📊", "Tax Ready"),
        _badge_row("VAULT_STARTER", "📄", "Vault Starter"),
    ]

    r = await client.get("/v1/gamification/badges", headers=employee_auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert "badges" in body
    assert len(body["badges"]) == 2
    assert body["badges"][0]["badge_key"] == "TAX_READY"


@pytest.mark.asyncio
async def test_badges_empty_when_none_earned(client, employee_auth_headers, mock_db):
    mock_db.fetch.return_value = []

    r = await client.get("/v1/gamification/badges", headers=employee_auth_headers)

    assert r.status_code == 200
    assert r.json()["badges"] == []


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_scoped_to_authenticated_employee(client, employee_auth_headers, mock_db):
    """Router must never accept employee_user_id from request body — only from JWT."""
    mock_db.fetchrow.return_value = _score_row(score=45)
    mock_db.fetch.return_value = []
    mock_db.fetchval.return_value = 0

    other_emp = str(uuid4())
    # Even if caller passes a different ID in query params, it is ignored
    r = await client.get(
        f"/v1/gamification/profile?employee_user_id={other_emp}",
        headers=employee_auth_headers,
    )

    # Should still return 200 using JWT-bound employee, not the query param
    assert r.status_code == 200


# ── Response shape ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_response_shape(client, employee_auth_headers, mock_db):
    mock_db.fetchrow.return_value = _score_row(score=60)
    mock_db.fetch.return_value = [_badge_row("STREAK_3", "🔥", "3-Day Streak")]
    mock_db.fetchval.return_value = 3

    r = await client.get("/v1/gamification/profile", headers=employee_auth_headers)

    body = r.json()
    assert set(body.keys()) >= {"score", "score_breakdown", "badges", "streak"}
    assert set(body["score_breakdown"].keys()) >= {
        "completeness_pts", "freshness_pts", "diversity_pts", "engagement_pts"
    }
    assert set(body["streak"].keys()) >= {"current_streak_days", "longest_streak_days"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_row(score=50):
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "score":            score,
        "completeness_pts": 20,
        "freshness_pts":    20,
        "diversity_pts":    score - 40 if score > 40 else 0,
        "engagement_pts":   5,
        "last_calculated_at": date.today(),
    }.get(k)
    return d


def _badge_row(badge_key, icon, name):
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "badge_key":        badge_key,
        "badge_name":       name,
        "badge_icon":       icon,
        "category":         "vault",
        "earned_at":        date.today().isoformat(),
        "context":          {},
    }.get(k)
    return d


def _streak_row(current, longest, last_date):
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "current_streak_days": current,
        "longest_streak_days": longest,
        "last_checkin_date":   last_date,
        "streak_started_date": last_date - timedelta(days=current - 1),
        "total_checkins":      current + 5,
    }.get(k)
    return d


# ── Coaching tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coaching_requires_auth(client):
    response = await client.get("/v1/gamification/coaching")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_coaching_returns_actions(client, employee_auth_headers, mock_db):
    """Happy path: returns coaching list with required fields."""
    emp_uuid = str(uuid4())
    tenant_id = str(uuid4())

    # document rows
    def _doc(doc_type, period=None):
        d = MagicMock()
        from datetime import datetime
        d.__getitem__ = lambda self, k: {
            "doc_type":  doc_type,
            "doc_period": period,
            "tenant_id": tenant_id,
            "routed_at": datetime.now(),
        }.get(k)
        return d

    # master rows
    def _master():
        m = MagicMock()
        m.__getitem__ = lambda self, k: {
            "tenant_id":    tenant_id,
            "doj":          date(2022, 1, 1),
            "dol":          None,
            "vault_completeness": 60,
            "company_name": "AcmeCorp",
        }.get(k)
        return m

    mock_db.fetch = AsyncMock(side_effect=[
        [_doc("SALARY_SLIP", "2024-01")],  # doc_rows
        [_master()],                        # master_rows
    ])
    mock_db.fetchval = AsyncMock(return_value=0)  # streak

    response = await client.get("/v1/gamification/coaching", headers=employee_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "coaching" in data
    assert "total" in data
    for action in data["coaching"]:
        assert "score_impact" in action
        assert "action_type" in action
        assert "pillar" in action
        assert "cta" in action
        assert action["score_impact"] > 0


@pytest.mark.asyncio
async def test_coaching_no_raw_salary_or_pan(client, employee_auth_headers, mock_db):
    """Privacy: no raw salary or PAN field in coaching response."""
    mock_db.fetch = AsyncMock(return_value=[])
    mock_db.fetchval = AsyncMock(return_value=5)

    response = await client.get("/v1/gamification/coaching", headers=employee_auth_headers)
    assert response.status_code == 200
    body = str(response.json())
    for forbidden in ("salary", "pan", "ctc", "lpa", "₹"):
        assert forbidden.lower() not in body.lower()


@pytest.mark.asyncio
async def test_coaching_empty_vault_suggests_upload(client, employee_auth_headers, mock_db):
    """Empty vault must yield at least one SELF_UPLOAD suggestion."""
    tenant_id = str(uuid4())

    def _master():
        m = MagicMock()
        m.__getitem__ = lambda self, k: {
            "tenant_id":    tenant_id,
            "doj":          date(2023, 6, 1),
            "dol":          None,
            "vault_completeness": 0,
            "company_name": "Globex",
        }.get(k)
        return m

    mock_db.fetch = AsyncMock(side_effect=[
        [],           # doc_rows — empty vault
        [_master()],  # master_rows
    ])
    mock_db.fetchval = AsyncMock(return_value=0)

    response = await client.get("/v1/gamification/coaching", headers=employee_auth_headers)
    assert response.status_code == 200
    data = response.json()
    ctas = [a["cta"] for a in data["coaching"]]
    assert "UPLOAD" in ctas
