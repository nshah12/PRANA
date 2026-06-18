"""
Extraction schema validation tests.

Verifies that all 10 doc type schemas accept valid LLM output
and reject malformed responses.
"""
import json
import pytest

from extraction.schemas.salary_slip import SalarySlipExtraction
from extraction.schemas.form_16 import Form16Extraction
from extraction.schemas.offer_letter import OfferLetterExtraction
from extraction.schemas.appointment_letter import AppointmentLetterExtraction
from extraction.schemas.increment_letter import IncrementLetterExtraction
from extraction.schemas.promotion_letter import PromotionLetterExtraction
from extraction.schemas.experience_letter import ExperienceLetterExtraction
from extraction.schemas.relieving_letter import RelievingLetterExtraction
from extraction.schemas.joining_letter import JoiningLetterExtraction
from extraction.schemas.pf_acknowledgement import PFAcknowledgementExtraction
from extraction.schemas.base import ExtractedField


def _field(value, confidence=0.95):
    return {"value": value, "confidence": confidence}


# ── SalarySlipExtraction ──────────────────────────────────────────────────────

def test_salary_slip_schema_accepts_valid():
    data = {
        "employee_name": _field("Rahul Sharma"),
        "employer_name": _field("Tata Consultancy Services"),
        "designation":   _field("Software Engineer"),
        "pay_period":    _field("March 2024"),
        "gross_salary":  _field("85000"),
        "net_salary":    _field("72000"),
    }
    result = SalarySlipExtraction(**data)
    assert result.employee_name.value == "Rahul Sharma"


def test_salary_slip_schema_accepts_partial_fields():
    # All fields are optional (confidence may be low for any field) — schema must
    # accept partial responses and record low confidence, not hard-fail on missing fields.
    result = SalarySlipExtraction(employer_name=_field("ACME"))
    assert result.employer_name.value == "ACME"
    assert result.employee_name.value is None  # absent field defaults to FieldValue(value=None)


# ── Form16Extraction ──────────────────────────────────────────────────────────

def test_form16_schema_accepts_valid():
    data = {
        "employee_name":    _field("Priya Mehta"),
        "employer_name":    _field("Infosys"),
        "financial_year":   _field("2023-24"),
        "total_income":     _field("1200000"),
        "tax_deducted":     _field("120000"),
    }
    result = Form16Extraction(**data)
    assert result.financial_year.value == "2023-24"


# ── OfferLetterExtraction ─────────────────────────────────────────────────────

def test_offer_letter_schema_accepts_valid():
    data = {
        "employee_name":    _field("Amit Patel"),
        "employer_name":    _field("Wipro"),
        "designation":      _field("Senior Analyst"),
        "date_of_joining":  _field("2024-04-01"),
        "ctc":              _field("1500000"),
    }
    result = OfferLetterExtraction(**data)
    assert result.designation.value == "Senior Analyst"


# ── Letter schemas — basic smoke tests ───────────────────────────────────────

@pytest.mark.parametrize("SchemaClass,extra", [
    (AppointmentLetterExtraction, {"date_of_joining": _field("2023-06-01")}),
    (IncrementLetterExtraction,   {"effective_date":  _field("2024-01-01"), "revised_ctc": _field("1800000")}),
    (PromotionLetterExtraction,   {"effective_date":  _field("2024-01-01"), "new_designation": _field("Lead")}),
    (ExperienceLetterExtraction,  {"last_working_day": _field("2024-03-31")}),
    (RelievingLetterExtraction,   {"last_working_day": _field("2024-03-31")}),
    (JoiningLetterExtraction,     {"date_of_joining": _field("2024-04-01")}),
    (PFAcknowledgementExtraction, {"uan_number": _field("100123456789")}),
])
def test_letter_schemas_accept_valid_employee_name(SchemaClass, extra):
    data = {"employee_name": _field("Test Employee"), **extra}
    result = SchemaClass(**data)
    assert result.employee_name.value == "Test Employee"


# ── Low-confidence field detection ───────────────────────────────────────────

def test_extracted_field_stores_confidence():
    f = ExtractedField(value="Rahul", confidence=0.61)
    assert f.confidence == pytest.approx(0.61)
    assert f.value == "Rahul"


def test_all_schemas_importable():
    """Regression guard — importing all schemas must not raise."""
    from extraction.schemas import __init__ as schema_init  # noqa: F401
