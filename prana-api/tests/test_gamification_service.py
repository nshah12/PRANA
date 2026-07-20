"""
RED tests for GamificationService.

Run BEFORE implementing the service — every test must fail first.
Each test verifies one contract from the service spec.
"""
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from services.gamification_service import GamificationService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def svc():
    return GamificationService()


@pytest.fixture
def emp_id():
    return uuid4()


def _doc(doc_type="SALARY_SLIP", routed_at_days_ago=10, is_deleted=False):
    """Return a mock asyncpg Record-like dict for a document row."""
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "doc_type": doc_type,
        "routed_at": date.today() - timedelta(days=routed_at_days_ago),
        "is_deleted": is_deleted,
    }[k]
    return d


def _em(tenant_id=None, doj=None, dol=None):
    """Mock employee_master row."""
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "tenant_id": tenant_id or uuid4(),
        "doj": doj or date(2018, 1, 1),
        "dol": dol,
        "vault_completeness": 80.0,
    }[k]
    return d


# ── Score calculation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_zero_for_no_docs(svc, emp_id):
    """Employee with no routed docs → score 0."""
    db = AsyncMock()
    db.fetch.return_value = []      # no docs
    db.fetchval.return_value = 0    # no checkins / streak

    result = await svc.recalculate_score(emp_id, db)

    assert result["score"] == 0
    assert result["completeness_pts"] == 0
    assert result["freshness_pts"] == 0
    assert result["diversity_pts"] == 0
    assert result["engagement_pts"] == 0


@pytest.mark.asyncio
async def test_freshness_full_pts_for_recent_doc(svc, emp_id):
    """Doc routed < 30 days ago → 30 freshness pts."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", routed_at_days_ago=5)],  # docs
        [],                                             # masters
    ]
    db.fetchval.return_value = 0

    result = await svc.recalculate_score(emp_id, db)

    assert result["freshness_pts"] == 30


@pytest.mark.asyncio
async def test_freshness_zero_for_stale_doc(svc, emp_id):
    """Doc routed > 180 days ago → 0 freshness pts."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", routed_at_days_ago=200)],
        [],
    ]
    db.fetchval.return_value = 0

    result = await svc.recalculate_score(emp_id, db)

    assert result["freshness_pts"] == 0


@pytest.mark.asyncio
async def test_diversity_caps_at_20(svc, emp_id):
    """10+ unique doc types → diversity_pts capped at 20."""
    doc_types = [
        "SALARY_SLIP", "FORM_16", "OFFER_LETTER", "APPOINTMENT_LETTER",
        "INCREMENT_LETTER", "PROMOTION_LETTER", "RELIEVING_LETTER",
        "EXPERIENCE_LETTER", "JOINING_LETTER", "PF_ACKNOWLEDGEMENT",
        "BANK_STATEMENT",
    ]
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc(dt, 5) for dt in doc_types],
        [],
    ]
    db.fetchval.return_value = 0

    result = await svc.recalculate_score(emp_id, db)

    assert result["diversity_pts"] == 20


@pytest.mark.asyncio
async def test_engagement_caps_at_10(svc, emp_id):
    """Streak of 50 days → engagement_pts capped at 10."""
    db = AsyncMock()
    db.fetch.side_effect = [[], []]
    db.fetchval.return_value = 50   # streak days

    result = await svc.recalculate_score(emp_id, db)

    assert result["engagement_pts"] == 10


@pytest.mark.asyncio
async def test_score_is_sum_of_components(svc, emp_id):
    """total score == sum of 4 component pts."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", 5), _doc("FORM_16", 5)],   # 2 doc types
        [_em()],                                          # 1 employer
    ]
    db.fetchval.return_value = 3   # 3-day streak

    result = await svc.recalculate_score(emp_id, db)

    assert result["score"] == (
        result["completeness_pts"]
        + result["freshness_pts"]
        + result["diversity_pts"]
        + result["engagement_pts"]
    )


@pytest.mark.asyncio
async def test_score_never_exceeds_100(svc, emp_id):
    """Score is bounded 0–100 regardless of inputs."""
    doc_types = [
        "SALARY_SLIP", "FORM_16", "OFFER_LETTER", "APPOINTMENT_LETTER",
        "INCREMENT_LETTER", "PROMOTION_LETTER", "RELIEVING_LETTER",
        "EXPERIENCE_LETTER", "JOINING_LETTER", "PF_ACKNOWLEDGEMENT",
    ]
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc(dt, 1) for dt in doc_types],
        [_em(), _em(), _em()],   # 3 employers
    ]
    db.fetchval.return_value = 100   # big streak

    result = await svc.recalculate_score(emp_id, db)

    assert 0 <= result["score"] <= 100


# ── Badge engine ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vault_starter_badge_awarded_on_first_doc(svc, emp_id):
    """VAULT_STARTER badge awarded when employee has >= 1 ROUTED doc."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", 5)],   # routed docs
        [],                          # masters
        [_make_badge_def("VAULT_STARTER")],   # badge definitions
        [],                          # already_earned
    ]
    db.fetchval.return_value = 0

    awarded = await svc.check_and_award_badges(emp_id, db)

    assert "VAULT_STARTER" in awarded


@pytest.mark.asyncio
async def test_tax_ready_badge_requires_form16(svc, emp_id):
    """TAX_READY badge only awarded when FORM_16 doc is present."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", 5)],   # only salary slip, no Form 16
        [],
        [_make_badge_def("TAX_READY")],
        [],
    ]
    db.fetchval.return_value = 0

    awarded = await svc.check_and_award_badges(emp_id, db)

    assert "TAX_READY" not in awarded


@pytest.mark.asyncio
async def test_multi_org_badge_requires_3_employers(svc, emp_id):
    """MULTI_ORG badge needs employee_master rows for 3+ distinct tenant_ids."""
    db = AsyncMock()
    t1, t2 = uuid4(), uuid4()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", 5)],
        [_em(t1), _em(t2)],    # only 2 employers — not enough
        [_make_badge_def("MULTI_ORG")],
        [],
    ]
    db.fetchval.return_value = 0

    awarded = await svc.check_and_award_badges(emp_id, db)

    assert "MULTI_ORG" not in awarded


@pytest.mark.asyncio
async def test_streak_3_badge_awarded_at_3_days(svc, emp_id):
    """STREAK_3 badge awarded when current_streak_days >= 3."""
    db = AsyncMock()
    db.fetch.side_effect = [
        [],
        [],
        [_make_badge_def("STREAK_3")],
        [],
    ]
    db.fetchval.return_value = 3   # current streak

    awarded = await svc.check_and_award_badges(emp_id, db)

    assert "STREAK_3" in awarded


@pytest.mark.asyncio
async def test_already_earned_badge_not_re_awarded(svc, emp_id):
    """Badge already in employee_badge is not awarded again."""
    badge_def_id = uuid4()
    db = AsyncMock()
    db.fetch.side_effect = [
        [_doc("SALARY_SLIP", 5)],
        [],
        [_make_badge_def("VAULT_STARTER", badge_def_id)],
        [{"badge_key": "VAULT_STARTER", "context_key": ""}],  # already earned
    ]
    db.fetchval.return_value = 0

    awarded = await svc.check_and_award_badges(emp_id, db)

    assert "VAULT_STARTER" not in awarded


# ── Streak tracking ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_checkin_starts_streak_at_1(svc, emp_id):
    """New employee first checkin → streak = 1."""
    db = AsyncMock()
    db.fetchrow.return_value = None  # no existing streak row

    result = await svc.update_streak(emp_id, db)

    assert result["current_streak_days"] == 1
    assert result["longest_streak_days"] == 1


@pytest.mark.asyncio
async def test_consecutive_day_increments_streak(svc, emp_id):
    """Checkin the day after last → streak increments."""
    yesterday = date.today() - timedelta(days=1)
    existing = _make_streak_row(current=5, longest=7, last_date=yesterday)
    db = AsyncMock()
    db.fetchrow.return_value = existing

    result = await svc.update_streak(emp_id, db)

    assert result["current_streak_days"] == 6


@pytest.mark.asyncio
async def test_same_day_checkin_does_not_change_streak(svc, emp_id):
    """Second checkin on the same day → streak unchanged."""
    today = date.today()
    existing = _make_streak_row(current=5, longest=7, last_date=today)
    db = AsyncMock()
    db.fetchrow.return_value = existing

    result = await svc.update_streak(emp_id, db)

    assert result["current_streak_days"] == 5


@pytest.mark.asyncio
async def test_missed_day_resets_streak(svc, emp_id):
    """Gap of 2+ days → streak resets to 1."""
    two_days_ago = date.today() - timedelta(days=2)
    existing = _make_streak_row(current=10, longest=10, last_date=two_days_ago)
    db = AsyncMock()
    db.fetchrow.return_value = existing

    result = await svc.update_streak(emp_id, db)

    assert result["current_streak_days"] == 1


@pytest.mark.asyncio
async def test_longest_streak_never_decreases(svc, emp_id):
    """Longest streak only goes up, never resets."""
    two_days_ago = date.today() - timedelta(days=2)
    existing = _make_streak_row(current=10, longest=15, last_date=two_days_ago)
    db = AsyncMock()
    db.fetchrow.return_value = existing

    result = await svc.update_streak(emp_id, db)

    assert result["longest_streak_days"] == 15   # preserved despite reset


# ── Privacy guard ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_result_contains_no_salary_fields(svc, emp_id):
    """Score response must not contain any raw financial field names."""
    db = AsyncMock()
    db.fetch.side_effect = [[], []]
    db.fetchval.return_value = 0

    result = await svc.recalculate_score(emp_id, db)

    forbidden = {"salary", "ctc", "inr", "amount", "rupee", "pay", "wage"}
    for key in result:
        assert key.lower() not in forbidden, f"Financial field '{key}' found in score result"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_badge_def(badge_key, badge_def_id=None):
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "badge_definition_id": badge_def_id or uuid4(),
        "badge_key": badge_key,
        "category": "vault",
    }[k]
    return d


def _make_streak_row(current, longest, last_date):
    d = MagicMock()
    d.__getitem__ = lambda self, k: {
        "current_streak_days": current,
        "longest_streak_days": longest,
        "last_checkin_date":   last_date,
        "streak_started_date": last_date - timedelta(days=current - 1),
        "total_checkins":      current,
    }[k]
    return d
