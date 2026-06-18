from .base import BaseExtraction, FieldValue


class InvestmentProofExtraction(BaseExtraction):
    """80C / 80D / HRA / LTA investment and exemption proof documents."""
    employee_name:      FieldValue = FieldValue()
    pan_number:         FieldValue = FieldValue()
    financial_year:     FieldValue = FieldValue()
    proof_type:         FieldValue = FieldValue()   # PPF | ELSS | LIC | HRA | LTA | NPS | 80D
    # Amounts — stripped before DB write by stage06
    declared_amount:    FieldValue = FieldValue()
    approved_amount:    FieldValue = FieldValue()
    provider_name:      FieldValue = FieldValue()   # bank / insurer / fund house
    policy_number:      FieldValue = FieldValue()
    receipt_date:       FieldValue = FieldValue()
    submission_date:    FieldValue = FieldValue()
    employer_name:      FieldValue = FieldValue()
