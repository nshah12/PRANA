"""
Tests for services/onboarding_service.py — tenant onboarding auto-approval tiering.

Rule (from the PA Onboarding Queue wireframe):
  Standard  · 1-500 employees, non-BFSI  -> auto-approved within minutes
  BFSI/Large· BFSI (any size) or 501-2000 -> PA manual review
  Enterprise· 2001+ employees             -> PA + Sales review

employee_headcount_band values come from CreateTenantWizard.tsx:
  '1-50','51-200','201-500','501-2000','2001-10000','10000+'
"""
import pytest

from services.onboarding_service import classify_onboarding_tier


@pytest.mark.parametrize("band", ["1-50", "51-200", "201-500"])
def test_auto_approval_approves_standard_non_bfsi_tenant(band):
    result = classify_onboarding_tier(industry="IT & Software", employee_headcount_band=band)
    assert result == "AUTO_APPROVE"


def test_auto_approval_flags_bfsi_for_review_even_at_small_headcount():
    result = classify_onboarding_tier(
        industry="Banking & Financial Services (BFSI)", employee_headcount_band="1-50"
    )
    assert result == "PA_REVIEW"


def test_auto_approval_flags_501_to_2000_for_review():
    result = classify_onboarding_tier(industry="IT & Software", employee_headcount_band="501-2000")
    assert result == "PA_REVIEW"


@pytest.mark.parametrize("band", ["2001-10000", "10000+"])
def test_auto_approval_flags_enterprise_for_sales_review(band):
    result = classify_onboarding_tier(industry="IT & Software", employee_headcount_band=band)
    assert result == "PA_SALES_REVIEW"


def test_auto_approval_enterprise_supersedes_non_bfsi():
    """Even a non-BFSI tenant at enterprise scale needs Sales review, not auto-approval."""
    result = classify_onboarding_tier(industry="Retail & FMCG", employee_headcount_band="10000+")
    assert result == "PA_SALES_REVIEW"


def test_auto_approval_missing_headcount_band_defaults_to_review():
    """Unknown/missing band must never silently auto-approve — fail safe to review."""
    result = classify_onboarding_tier(industry="IT & Software", employee_headcount_band="")
    assert result == "PA_REVIEW"
