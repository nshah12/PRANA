from pydantic import Field
from .base import BaseExtraction, FieldValue


class ExperienceLetterExtraction(BaseExtraction):
    employer_name:   FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:   FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    designation:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    department:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_joining: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_leaving: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    tenure_text:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    conduct:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
