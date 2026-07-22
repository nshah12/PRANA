"""Tests for services/statutory_hold_service.py — compute_hold_until logic."""
from datetime import date
import pytest
from services.statutory_hold_service import compute_hold_until


def test_salary_slip_hold_5_years():
    pushed = date(2020, 4, 1)
    reason, until = compute_hold_until("SALARY_SLIP", pushed)
    assert reason == "EPF_ACT"
    assert until == date(2025, 4, 1)


def test_form16_hold_7_years():
    pushed = date(2020, 4, 1)
    reason, until = compute_hold_until("FORM_16", pushed)
    assert reason == "INCOME_TAX_ACT"
    assert until == date(2027, 4, 1)


def test_offer_letter_hold_8_years():
    pushed = date(2019, 6, 15)
    reason, until = compute_hold_until("OFFER_LETTER", pushed)
    assert reason == "COMPANIES_ACT"
    assert until == date(2027, 6, 15)


def test_appraisal_letter_no_hold():
    reason, until = compute_hold_until("APPRAISAL_LETTER", date(2020, 1, 1))
    assert reason is None
    assert until is None


def test_self_upload_no_hold():
    reason, until = compute_hold_until("SELF_UPLOAD", date(2024, 3, 1))
    assert reason is None
    assert until is None


def test_unknown_doc_type_no_hold():
    reason, until = compute_hold_until("UNKNOWN_DOC", date(2024, 1, 1))
    assert reason is None
    assert until is None


def test_relieving_letter_hold_5_years():
    pushed = date(2022, 9, 1)
    reason, until = compute_hold_until("RELIEVING_LETTER", pushed)
    assert reason == "GRATUITY_ACT"
    assert until == date(2027, 9, 1)


def test_pf_acknowledgement_hold_5_years():
    pushed = date(2021, 3, 31)
    reason, until = compute_hold_until("PF_ACKNOWLEDGEMENT", pushed)
    assert reason == "EPF_ACT"
    assert until == date(2026, 3, 31)
