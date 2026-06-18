from pydantic import Field
from .base import BaseExtraction, FieldValue


class RelievingLetterExtraction(BaseExtraction):
    employer_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    designation:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_joining:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    last_working_day: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    reason:           FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    notice_period:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    full_settlement:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
