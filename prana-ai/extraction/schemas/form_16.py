from .base import BaseExtraction, FieldValue


class Form16Extraction(BaseExtraction):
    employee_name:      FieldValue = FieldValue()
    pan_number:         FieldValue = FieldValue()
    employer_name:      FieldValue = FieldValue()
    employer_tan:       FieldValue = FieldValue()
    employer_address:   FieldValue = FieldValue()
    assessment_year:    FieldValue = FieldValue()
    financial_year:     FieldValue = FieldValue()
    gross_salary:       FieldValue = FieldValue()
    total_tds:          FieldValue = FieldValue()
    net_taxable_income: FieldValue = FieldValue()
    section_80c:        FieldValue = FieldValue()
    section_80d:        FieldValue = FieldValue()
    hra_exemption:      FieldValue = FieldValue()
