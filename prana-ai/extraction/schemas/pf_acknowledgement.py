from pydantic import Field
from .base import BaseExtraction, FieldValue


class PFAcknowledgementExtraction(BaseExtraction):
    employer_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employee_name:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    uan:              FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    pf_account_no:    FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    # Already redacted to [NIK_REDACTED] at OCR time (stage04_extract.py's PAN
    # regex) before this ever reaches the LLM — never the raw PAN.
    pan_number:       FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    establishment_id: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    member_id:        FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_joining:  FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    date_of_exit:     FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    acknowledgement_date: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    contribution_month: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    # NOTE: employee_share and employer_share extracted for pipeline only.
    # benchmark_service is the only consumer. Never stored or returned in API.
    employee_share:   FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    employer_share:   FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    acknowledgement_no: FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
    filing_date:      FieldValue = Field(default_factory=lambda: FieldValue(value=None, confidence=0.0))
