from pydantic import Field
from .base import BaseExtraction, FieldValue


class AppointmentLetterExtraction(BaseExtraction):
    employer_name:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    designation:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    department:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_appointment: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_joining:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employment_type:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    grade:               FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    grade_band:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    location:            FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    probation_period:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    probation_months:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    notice_period_days:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    reporting_to:        FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_id:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    letter_date:         FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    # NOTE: ctc_annual is extracted for pipeline use only (benchmark_service
    # consumption) — stripped before DB write; deliberately absent from
    # stage06_route._SAFE_METADATA_FIELDS.
    ctc_annual:          FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
