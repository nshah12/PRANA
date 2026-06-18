from .base import BaseExtraction, FieldValue


class ITReturnExtraction(BaseExtraction):
    """ITR-1 / ITR-2 / ITR-4 — Annual income tax return."""
    assessment_year:        FieldValue = FieldValue()
    pan_number:             FieldValue = FieldValue()
    employee_name:          FieldValue = FieldValue()
    gross_total_income:     FieldValue = FieldValue()   # stripped before DB write
    total_deductions_80c:   FieldValue = FieldValue()   # stripped before DB write
    taxable_income:         FieldValue = FieldValue()   # stripped before DB write
    tax_payable:            FieldValue = FieldValue()   # stripped before DB write
    tds_deducted:           FieldValue = FieldValue()   # stripped before DB write
    refund_due:             FieldValue = FieldValue()   # stripped before DB write
    itr_form_type:          FieldValue = FieldValue()   # ITR-1, ITR-2, ITR-4
    filing_date:            FieldValue = FieldValue()
    acknowledgement_number: FieldValue = FieldValue()
    employer_name:          FieldValue = FieldValue()
    employer_tan:           FieldValue = FieldValue()
