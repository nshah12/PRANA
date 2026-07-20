"""
Statutory retention logic — DPDP Act erasure vs Indian labour law conflict.

When an employee requests erasure under DPDP Act Section 12, certain documents
cannot be deleted because the employer has a statutory obligation to retain them
under Indian labour law. DPDP Act Section 9(11) explicitly permits retention when
required by law.

This module is the single source of truth for which doc_types carry a statutory
hold and for how long.
"""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

# (statutory_act_identifier, retention_years)
# None means no statutory hold — employee erasure applies in full.
_DOC_TYPE_RETENTION: dict[str, tuple[str, int] | None] = {
    "SALARY_SLIP":        ("EPF_ACT",                5),  # EPF & MP Act 1952
    "FORM_16":            ("INCOME_TAX_ACT",          7),  # Income Tax Act 1961
    "FORM_12B":           ("INCOME_TAX_ACT",          7),
    "FORM_26AS":          ("INCOME_TAX_ACT",          7),
    "IT_RETURN":          ("INCOME_TAX_ACT",          7),
    "OFFER_LETTER":       ("COMPANIES_ACT",           8),  # Companies Act 2013
    "APPOINTMENT_LETTER": ("COMPANIES_ACT",           8),
    "RELIEVING_LETTER":   ("GRATUITY_ACT",            5),  # Payment of Gratuity Act 1972
    "EXPERIENCE_LETTER":  ("GRATUITY_ACT",            5),
    "GRATUITY_LETTER":    ("GRATUITY_ACT",            5),
    "PF_ACKNOWLEDGEMENT": ("EPF_ACT",                 5),
    "BONUS_LETTER":       ("PAYMENT_OF_BONUS_ACT",    5),  # Payment of Bonus Act 1965
    # No statutory hold — full erasure applies:
    "APPRAISAL_LETTER":   None,
    "INCREMENT_LETTER":   None,
    "PROMOTION_LETTER":   None,
    "JOINING_LETTER":     None,
    "BANK_STATEMENT":     None,
    "INVESTMENT_PROOF":   None,
    "SELF_UPLOAD":        None,
}


def compute_hold_until(doc_type: str, pushed_at: date) -> tuple[str | None, date | None]:
    """
    Return (statutory_act_identifier, hold_until_date) for a document type.
    Returns (None, None) if the doc_type has no statutory hold.

    hold_until_date is calculated from pushed_at (the date the employer uploaded
    the document), not from dol or any other date — the obligation starts on upload.
    """
    entry = _DOC_TYPE_RETENTION.get(doc_type)
    if not entry:
        return None, None
    reason, years = entry
    return reason, pushed_at + relativedelta(years=years)
