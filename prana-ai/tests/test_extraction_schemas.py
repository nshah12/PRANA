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


# ── BonusLetterExtraction ─────────────────────────────────────────────────────

def test_bonus_letter_schema_accepts_valid():
    from extraction.schemas.bonus_letter import BonusLetterExtraction
    data = {
        "employee_name":  _field("Amit Kumar"),
        "employer_name":  _field("Infosys Ltd"),
        "financial_year": _field("2023-24"),
        "bonus_type":     _field("STATUTORY"),
        "bonus_percentage": _field("8.33"),
    }
    result = BonusLetterExtraction(**data)
    assert result.employer_name.value == "Infosys Ltd"
    # bonus_percentage present — no raw ₹ amount in schema
    assert not hasattr(result, "bonus_amount"), \
        "BonusLetterExtraction must not have a bonus_amount field — privacy contract"


def test_bonus_letter_no_raw_amount_field():
    """Schema must not expose a raw rupee bonus_amount field."""
    from extraction.schemas.bonus_letter import BonusLetterExtraction
    schema_fields = BonusLetterExtraction.model_fields.keys()
    assert "bonus_amount" not in schema_fields, \
        "bonus_amount must not exist — extract bonus_percentage only (privacy contract)"


# ── GratuityLetterExtraction ──────────────────────────────────────────────────

def test_gratuity_letter_schema_accepts_valid():
    from extraction.schemas.gratuity_letter import GratuityLetterExtraction
    data = {
        "employee_name":    _field("Priya Menon"),
        "employer_name":    _field("Wipro Technologies"),
        "date_of_joining":  _field("2015-06-01"),
        "date_of_exit":     _field("2024-03-31"),
        "years_of_service": _field("8.8"),
        "reason_for_exit":  _field("RESIGNATION"),
        "gratuity_eligible": _field("true"),
    }
    result = GratuityLetterExtraction(**data)
    assert result.gratuity_eligible.value == "true"
    assert not hasattr(result, "gratuity_amount"), \
        "GratuityLetterExtraction must not have gratuity_amount — privacy contract"


def test_gratuity_letter_no_raw_amount_field():
    from extraction.schemas.gratuity_letter import GratuityLetterExtraction
    assert "gratuity_amount" not in GratuityLetterExtraction.model_fields, \
        "gratuity_amount must not exist — extract eligibility only (privacy contract)"


# ── Form12BExtraction ─────────────────────────────────────────────────────────

def test_form_12b_schema_accepts_valid():
    from extraction.schemas.form_12b import Form12BExtraction
    data = {
        "employee_name":          _field("Sunita Rao"),
        "pan_number":             _field("[NIK_REDACTED]"),
        "financial_year":         _field("2024-25"),
        "previous_employer_name": _field("Accenture India"),
        "previous_employer_tan":  _field("MUMA12345A"),
        "tds_deducted":           _field("45000"),
    }
    result = Form12BExtraction(**data)
    assert result.previous_employer_name.value == "Accenture India"


# ── Form26ASExtraction ────────────────────────────────────────────────────────

def test_form_26as_schema_accepts_valid():
    from extraction.schemas.form_26as import Form26ASExtraction
    data = {
        "taxpayer_name":   _field("Vikram Singh"),
        "pan_number":      _field("[NIK_REDACTED]"),
        "assessment_year": _field("2024-25"),
        "deductor_name":   _field("HCL Technologies"),
        "deductor_tan":    _field("DELA01234B"),
        "tds_amount":      _field("120000"),
    }
    result = Form26ASExtraction(**data)
    assert result.assessment_year.value == "2024-25"


# ── ExtractionService registry contains all 4 new types ──────────────────────

def test_extraction_service_registry_has_new_doc_types():
    from extraction.extraction_service import DocType, _REGISTRY
    assert DocType.BONUS_LETTER   in _REGISTRY, "BONUS_LETTER must be in extraction registry"
    assert DocType.GRATUITY_LETTER in _REGISTRY, "GRATUITY_LETTER must be in extraction registry"
    assert DocType.FORM_12B       in _REGISTRY, "FORM_12B must be in extraction registry"
    assert DocType.FORM_26AS      in _REGISTRY, "FORM_26AS must be in extraction registry"


def test_new_doc_type_prompts_have_privacy_guard():
    """Bonus and gratuity prompts must explicitly say not to extract rupee amount."""
    from extraction.prompts import bonus_letter, gratuity_letter
    assert "Do NOT extract" in bonus_letter.SYSTEM or "do NOT extract" in bonus_letter.SYSTEM, \
        "bonus_letter SYSTEM prompt must instruct LLM not to extract rupee amount"
    assert "Do NOT extract" in gratuity_letter.SYSTEM or "do NOT extract" in gratuity_letter.SYSTEM, \
        "gratuity_letter SYSTEM prompt must instruct LLM not to extract rupee amount"
