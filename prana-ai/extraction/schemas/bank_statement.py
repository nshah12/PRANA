from .base import BaseExtraction, FieldValue


class BankStatementExtraction(BaseExtraction):
    """Bank account statement — salary credit verification."""
    bank_name:          FieldValue = FieldValue()
    account_number:     FieldValue = FieldValue()   # masked, last 4 digits only
    account_holder:     FieldValue = FieldValue()
    ifsc_code:          FieldValue = FieldValue()
    statement_from:     FieldValue = FieldValue()   # ISO date
    statement_to:       FieldValue = FieldValue()   # ISO date
    # Salary credits — raw amounts stripped before DB write by stage06
    salary_credit_count: FieldValue = FieldValue()  # number of credits matching salary pattern
    avg_monthly_credit: FieldValue = FieldValue()   # stripped before DB write
    min_monthly_credit: FieldValue = FieldValue()   # stripped before DB write
    max_monthly_credit: FieldValue = FieldValue()   # stripped before DB write
    employer_name:      FieldValue = FieldValue()   # inferred from narration
    credit_dates:       FieldValue = FieldValue()   # comma-separated ISO dates
