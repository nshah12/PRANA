from .base import BaseExtraction, FieldValue


class SalarySlipExtraction(BaseExtraction):
    employee_id:      FieldValue = FieldValue()
    employee_name:    FieldValue = FieldValue()
    designation:      FieldValue = FieldValue()
    department:       FieldValue = FieldValue()
    location:         FieldValue = FieldValue()
    gross_ctc:        FieldValue = FieldValue()
    basic_salary:     FieldValue = FieldValue()
    hra:              FieldValue = FieldValue()
    pf_employee:      FieldValue = FieldValue()
    tds_amount:       FieldValue = FieldValue()
    net_pay:          FieldValue = FieldValue()
    pf_number:        FieldValue = FieldValue()
    uan_number:       FieldValue = FieldValue()
    pan_number:       FieldValue = FieldValue()
    pay_period_month: FieldValue = FieldValue()
    pay_period_year:  FieldValue = FieldValue()
    employer_name:    FieldValue = FieldValue()
