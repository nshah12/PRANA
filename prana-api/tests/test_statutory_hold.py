"""
Statutory hold tests — DPDP Act erasure vs Indian labour law retention conflict.

These tests cover:
  1. ComplianceService.execute_erasure() respects statutory holds
  2. Vault document listing respects employee_visible column

compute_hold_until() itself is covered in test_statutory_hold_service.py (the
TDD-01-canonical test file for services/statutory_hold_service.py) — this file
used to duplicate that coverage in a TestComputeHoldUntil class with the same
doc_type/date combinations; consolidated 2026-08-10, see that file for the
retention-period test cases (it also covers test_unknown_doc_type_no_hold,
which this file never did).

RED → GREEN cycle: written before implementation.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ── 2. execute_erasure() splits docs into held vs free ───────────────────────

@pytest.mark.asyncio
async def test_execute_erasure_soft_deletes_free_docs_only():
    """
    Documents WITHOUT active statutory hold → is_deleted=TRUE, employee_visible=FALSE.
    Documents WITH active statutory hold    → employee_visible=FALSE ONLY (not deleted).
    RED: fails until execute_erasure() is updated to check statutory_hold_until.
    """
    from services.compliance_service import ComplianceService

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock()
    mock_db.transaction = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    )

    today = date.today()
    future_hold = date(today.year + 5, today.month, today.day)  # 5 years from now

    mock_db.fetch = AsyncMock(return_value=[
        # Free doc — no statutory hold
        {"document_id": "doc-free-001", "s3_key": "staging/aa/t1/doc-free-001.pdf",
         "statutory_hold_until": None},
        # Held doc — active statutory hold
        {"document_id": "doc-held-002", "s3_key": "staging/bb/t1/doc-held-002.pdf",
         "statutory_hold_until": future_hold},
    ])

    svc = ComplianceService(db=mock_db)
    result = await svc.execute_erasure("emp-user-001")

    assert result["erased_count"] == 1, "One free doc should be erased"
    assert result["held_count"] == 1, "One doc should be held (statutory)"
    assert result["held_until"] == future_hold

    # Verify the free doc got is_deleted=TRUE
    execute_calls = [str(c) for c in mock_db.execute.call_args_list]
    any_free_delete = any(
        "is_deleted=TRUE" in c and "employee_visible=FALSE" in c
        for c in execute_calls
    )
    assert any_free_delete, "Free docs must get is_deleted=TRUE AND employee_visible=FALSE"

    # Verify the held doc got only employee_visible=FALSE (NOT is_deleted=TRUE)
    # The held doc should NOT appear in any is_deleted=TRUE UPDATE
    any_held_delete = any(
        "doc-held-002" in c and "is_deleted=TRUE" in c
        for c in execute_calls
    )
    assert not any_held_delete, "Held docs must NOT be soft-deleted — only hidden from employee"


@pytest.mark.asyncio
async def test_execute_erasure_returns_held_until_date():
    """
    execute_erasure must return {erased_count, held_count, held_until}.
    held_until must be the max statutory_hold_until across all held documents.
    RED: fails because current execute_erasure returns None.
    """
    from services.compliance_service import ComplianceService

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock()
    mock_db.transaction = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    )

    today = date.today()
    hold_2028 = date(today.year + 4, 1, 1)
    hold_2030 = date(today.year + 6, 1, 1)

    mock_db.fetch = AsyncMock(return_value=[
        {"document_id": "d1", "s3_key": "k1", "statutory_hold_until": hold_2028},
        {"document_id": "d2", "s3_key": "k2", "statutory_hold_until": hold_2030},
        {"document_id": "d3", "s3_key": "k3", "statutory_hold_until": None},
    ])

    svc = ComplianceService(db=mock_db)
    result = await svc.execute_erasure("emp-user-001")

    assert result is not None, "execute_erasure must return a result dict"
    assert result["held_until"] == hold_2030, "held_until must be the LATEST hold date"
    assert result["erased_count"] == 1
    assert result["held_count"] == 2


@pytest.mark.asyncio
async def test_execute_erasure_all_free_returns_zero_held():
    """When all documents have no statutory hold, held_count must be 0."""
    from services.compliance_service import ComplianceService

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.fetchval = AsyncMock()
    mock_db.transaction = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    )
    mock_db.fetch = AsyncMock(return_value=[
        {"document_id": "d1", "s3_key": "k1", "statutory_hold_until": None},
        {"document_id": "d2", "s3_key": "k2", "statutory_hold_until": None},
    ])

    svc = ComplianceService(db=mock_db)
    result = await svc.execute_erasure("emp-user-001")
    assert result["held_count"] == 0
    assert result["held_until"] is None


# ── 3. Statutory hold inferred at ingest time ─────────────────────────────────

def test_ingest_writes_statutory_hold_for_form16():
    """
    After INSERT document, ingest must UPDATE statutory_hold_until for held doc types.
    RED: fails until _ingest_one() calls compute_hold_until() and writes the columns.
    """
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "routers" / "ingest.py").read_text(encoding="utf-8")
    assert "statutory_hold_until" in src, \
        "_ingest_one() must write statutory_hold_until at upload time"
    assert "compute_hold_until" in src, \
        "_ingest_one() must call compute_hold_until() from statutory_hold_service"


# ── 4. Vault listing respects employee_visible ────────────────────────────────

def test_vault_query_filters_employee_visible():
    """
    Vault document listing query must include AND employee_visible=TRUE.
    Without this, erased-but-held documents remain visible to the employee.
    RED: fails until vault.py adds employee_visible filter to document queries.
    """
    import pathlib
    vault_src = (pathlib.Path(__file__).parent.parent / "routers" / "vault.py").read_text(encoding="utf-8")
    assert "employee_visible" in vault_src, \
        "vault.py document queries must filter AND employee_visible=TRUE"


def test_portal_query_filters_employer_visible():
    """
    Portal document listing must include AND employer_visible=TRUE.
    This maintains employer access to held documents during statutory period.
    RED: fails until portal router adds employer_visible filter.
    """
    import pathlib
    # Find the portal router that lists employer documents
    portal_files = list((pathlib.Path(__file__).parent.parent / "routers").glob("*.py"))
    portal_src = " ".join(f.read_text(encoding="utf-8") for f in portal_files)
    assert "employer_visible" in portal_src, \
        "Portal document queries must filter AND employer_visible=TRUE"
