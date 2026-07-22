from pydantic import Field
from .base import BaseExtraction, FieldValue


class PromotionLetterExtraction(BaseExtraction):
    employer_name:        FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:        FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    previous_designation: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    new_designation:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    previous_grade:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    new_grade:            FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    effective_date:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    department:           FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    # NOTE: ctc_new is extracted for pipeline use only (benchmark_service
    # consumption) — stripped before DB write; deliberately absent from
    # stage06_route._SAFE_METADATA_FIELDS.
    ctc_new:              FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
