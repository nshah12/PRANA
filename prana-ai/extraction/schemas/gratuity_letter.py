from typing import Optional
from .base import BaseExtraction, FieldValue


class GratuityLetterExtraction(BaseExtraction):
    employee_name: FieldValue = FieldValue()
    employee_id: FieldValue = FieldValue()
    employer_name: FieldValue = FieldValue()
    date_of_joining: FieldValue = FieldValue()
    date_of_exit: FieldValue = FieldValue()
    years_of_service: FieldValue = FieldValue()
    reason_for_exit: FieldValue = FieldValue()
    gratuity_eligible: FieldValue = FieldValue()
    acknowledgement_no: FieldValue = FieldValue()
