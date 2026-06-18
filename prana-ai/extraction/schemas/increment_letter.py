from pydantic import Field
from .base import BaseExtraction, FieldValue


class IncrementLetterExtraction(BaseExtraction):
    employer_name:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    designation:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    effective_date:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    increment_percent:   FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    # NOTE: ctc_before and ctc_after are extracted for pipeline use only.
    # benchmark_service consumes them to produce percentile labels.
    # These values are NEVER stored in extracted_fields or returned in any API response.
    ctc_before:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    ctc_after:           FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    grade:               FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    performance_rating:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
