from typing import Optional
from .base import BaseExtraction, FieldValue


class Form26ASExtraction(BaseExtraction):
    taxpayer_name: FieldValue = FieldValue()
    pan_number: FieldValue = FieldValue()
    assessment_year: FieldValue = FieldValue()
    deductor_name: FieldValue = FieldValue()
    deductor_tan: FieldValue = FieldValue()
    tds_amount: FieldValue = FieldValue()
    tcs_amount: FieldValue = FieldValue()
    advance_tax: FieldValue = FieldValue()
    self_assessment_tax: FieldValue = FieldValue()
    refund_amount: FieldValue = FieldValue()
