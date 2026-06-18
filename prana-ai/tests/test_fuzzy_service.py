"""Tests for resolution/fuzzy_service.py — name matching thresholds."""
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from resolution.fuzzy_service import FuzzyService, MATCH_THRESHOLD, POSSIBLE_THRESHOLD


_EMP_UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_TENANT   = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.mark.asyncio
async def test_fuzzy_match_name_doj_returns_score():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"employee_uuid": _EMP_UUID, "display_name": "Rahul Sharma", "doj": None},
    ])
    svc = FuzzyService(db)
    emp_uuid, score = await svc.match(_TENANT, "Sharma Rahul", doj=None)
    # token_sort_ratio("Sharma Rahul", "Rahul Sharma") = 100 — exact word match reordered
    assert score >= MATCH_THRESHOLD, f"Expected score >= {MATCH_THRESHOLD}, got {score}"
    assert emp_uuid == _EMP_UUID


@pytest.mark.asyncio
async def test_fuzzy_below_threshold_returns_no_match():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"employee_uuid": _EMP_UUID, "display_name": "Rahul Sharma", "doj": None},
    ])
    svc = FuzzyService(db)
    # Completely different name — score will be well below POSSIBLE_THRESHOLD
    emp_uuid, score = await svc.match(_TENANT, "Priya Nair", doj=None)
    assert emp_uuid is None, "Unrelated name must return no match"
    assert score < POSSIBLE_THRESHOLD, \
        f"Score {score} should be below POSSIBLE_THRESHOLD={POSSIBLE_THRESHOLD} for an unrelated name"
