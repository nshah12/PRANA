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
