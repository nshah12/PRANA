from .base import BaseExtraction, FieldValue


class OfferLetterExtraction(BaseExtraction):
    employee_name:     FieldValue = FieldValue()
    designation:       FieldValue = FieldValue()
    department:        FieldValue = FieldValue()
    location:          FieldValue = FieldValue()
    employer_name:     FieldValue = FieldValue()
    date_of_offer:     FieldValue = FieldValue()
    date_of_joining:   FieldValue = FieldValue()
    ctc_annual:        FieldValue = FieldValue()
    ctc_monthly:       FieldValue = FieldValue()
    probation_months:  FieldValue = FieldValue()
    notice_period_days:FieldValue = FieldValue()
    employee_id:       FieldValue = FieldValue()
    reporting_manager: FieldValue = FieldValue()
