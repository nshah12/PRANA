from .base import BaseExtraction, FieldValue


class AppraisalLetterExtraction(BaseExtraction):
    """Annual / mid-year appraisal letter — performance rating + increment details."""
    employee_name:          FieldValue = FieldValue()
    employee_id:            FieldValue = FieldValue()
    designation:            FieldValue = FieldValue()
    department:             FieldValue = FieldValue()
    appraisal_period:       FieldValue = FieldValue()   # "FY 2024-25"
    performance_rating:     FieldValue = FieldValue()   # "Exceeds Expectations", 4/5, etc.
    performance_band:       FieldValue = FieldValue()   # A / B+ / B / C
    effective_date:         FieldValue = FieldValue()   # increment effective from
    # Compensation — stripped before DB write by stage06
    previous_ctc:           FieldValue = FieldValue()
    revised_ctc:            FieldValue = FieldValue()
    increment_percentage:   FieldValue = FieldValue()   # kept as index (% not ₹)
    variable_component:     FieldValue = FieldValue()
    employer_name:          FieldValue = FieldValue()
    manager_name:           FieldValue = FieldValue()
    hr_name:                FieldValue = FieldValue()
