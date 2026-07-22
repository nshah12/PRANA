from typing import Optional
from .base import BaseExtraction, FieldValue


class BonusLetterExtraction(BaseExtraction):
    employee_name: FieldValue = FieldValue()
    employee_id: FieldValue = FieldValue()
    employer_name: FieldValue = FieldValue()
    financial_year: FieldValue = FieldValue()
    bonus_type: FieldValue = FieldValue()
    bonus_percentage: FieldValue = FieldValue()
    payment_date: FieldValue = FieldValue()
    eligible_months: FieldValue = FieldValue()
