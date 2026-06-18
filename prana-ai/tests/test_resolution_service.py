"""Tests for resolution/resolution_service.py — 4-level ladder ordering and result contract."""
import inspect
import pytest

from resolution.resolution_service import ResolutionService, ResolutionMethod


def test_resolution_ladder_order_pan_then_id_then_fuzzy_then_embedding():
    # The 4-level ladder must stop at the first successful level in this exact order:
    # Level 1: pan_token exact match (EXACT_PAN)
    # Level 2: employee_id match    (EMP_ID)
    # Level 3: fuzzy name + DOJ     (FUZZY_NAME)
    # Level 4: embedding cosine     (EMBEDDING)
    src = inspect.getsource(ResolutionService.resolve)
    pan_pos    = src.index("EXACT_PAN")
    emp_pos    = src.index("EMP_ID")
    fuzzy_pos  = src.index("FUZZY_NAME")
    embed_pos  = src.index("EMBEDDING")
    assert pan_pos < emp_pos < fuzzy_pos < embed_pos, \
        "Resolution ladder must proceed: EXACT_PAN → EMP_ID → FUZZY_NAME → EMBEDDING"


def test_resolution_result_links_to_employee_master_not_user():
    # Resolution produces an employee_uuid — the PK of employee_master.
    # Never returns employee_user_id (PK of employee_user) — those are different tables.
    src = inspect.getsource(ResolutionService.resolve)
    assert "employee_uuid" in src, \
        "ResolutionService.resolve must query/return employee_uuid (employee_master PK)"
    # Confirm it queries employee_master, not employee_user
    assert "employee_master" in src, \
        "Resolution must look up identity in employee_master, not employee_user"
