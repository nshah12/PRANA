from pydantic import Field
from .base import BaseExtraction, FieldValue


class JoiningLetterExtraction(BaseExtraction):
    employer_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    designation:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    department:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_joining:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    location:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    reporting_to:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
