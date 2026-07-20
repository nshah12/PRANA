"""
Tenant onboarding auto-approval tiering.

Rule (PA Onboarding Queue):
  Standard   1-500 employees, non-BFSI  -> auto-approved
  BFSI/Large BFSI (any size) or 501-2000 -> PA manual review
  Enterprise 2001+ employees             -> PA + Sales review

employee_headcount_band values (CreateTenantWizard.tsx):
  '1-50','51-200','201-500','501-2000','2001-10000','10000+'
"""
_BFSI_INDUSTRY = "Banking & Financial Services (BFSI)"
_STANDARD_BANDS = {"1-50", "51-200", "201-500"}
_LARGE_BANDS = {"501-2000"}
_ENTERPRISE_BANDS = {"2001-10000", "10000+"}


def classify_onboarding_tier(industry: str, employee_headcount_band: str) -> str:
    """Returns 'AUTO_APPROVE' | 'PA_REVIEW' | 'PA_SALES_REVIEW'."""
    if employee_headcount_band in _ENTERPRISE_BANDS:
        return "PA_SALES_REVIEW"
    if industry == _BFSI_INDUSTRY or employee_headcount_band in _LARGE_BANDS:
        return "PA_REVIEW"
    if employee_headcount_band in _STANDARD_BANDS:
        return "AUTO_APPROVE"
    return "PA_REVIEW"
