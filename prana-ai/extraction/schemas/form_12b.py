from typing import Optional
from .base import BaseExtraction, FieldValue


class Form12BExtraction(BaseExtraction):
    employee_name: FieldValue = FieldValue()
    pan_number: FieldValue = FieldValue()
    financial_year: FieldValue = FieldValue()
    previous_employer_name: FieldValue = FieldValue()
    previous_employer_tan: FieldValue = FieldValue()
    date_of_joining_prev: FieldValue = FieldValue()
    date_of_leaving_prev: FieldValue = FieldValue()
    tds_deducted: FieldValue = FieldValue()
    period_of_employment: FieldValue = FieldValue()
