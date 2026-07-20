-- Migration 020: Employee-centric labour-law document types
-- Adds platform-default field manifests for:
--   BONUS_LETTER      — annual bonus under Payment of Bonus Act 1965
--   GRATUITY_LETTER   — gratuity settlement (eligibility after 5 years of service)
--   FORM_12B          — previous-employer TDS declaration given to new employer
--   FORM_26AS         — TDS credit statement issued by Income Tax Dept (Annual)
--
-- These are employee-centric: each document belongs to one employee in the vault.
-- Employer-level filings (ESIC challan, PF ECR) are NOT added here —
-- they belong in compliance_obligation (see migration 019).
--
-- ROLLBACK:
--   DELETE FROM doc_type_field_manifest
--   WHERE tenant_id IS NULL
--     AND doc_type IN ('BONUS_LETTER','GRATUITY_LETTER','FORM_12B','FORM_26AS');

INSERT INTO doc_type_field_manifest
  (tenant_id, doc_type, required_fields, identity_fields, optional_fields,
   classification_signals, min_confidence_threshold, supported_formats)
VALUES

-- BONUS_LETTER
-- Payment of Bonus Act 1965: employer issues to all eligible employees (salary ≤ ₹21,000/month)
-- Key fields: employee name, bonus amount (NEVER stored raw — insight only), financial year
(NULL, 'BONUS_LETTER',
 '["employee_name","employer_name","financial_year","bonus_type"]',
 '["employee_id","employee_name","pan_number"]',
 '["designation","department","basic_salary_band","bonus_percentage","payment_date","arrear_flag"]',
 '[["financial_year","bonus_type","employer_name"],["employee_id","financial_year"]]',
 0.72,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- GRATUITY_LETTER
-- Payment of Gratuity Act 1972: issued on separation after ≥5 years of continuous service
-- Key fields: employee name, date of joining, date of exit, years of service, gratuity eligibility
-- Raw ₹ gratuity amount → insight only (never stored). Eligibility flag is stored.
(NULL, 'GRATUITY_LETTER',
 '["employee_name","employer_name","date_of_joining","date_of_exit","years_of_service"]',
 '["employee_id","employee_name","pan_number"]',
 '["designation","department","gratuity_eligible","payment_mode","bank_account_last4","utr_number"]',
 '[["date_of_joining","date_of_exit","years_of_service"],["employer_name","employee_id","gratuity_eligible"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- FORM_12B
-- Income Tax Rule 26A: employee gives to new employer on joining mid-year
-- Declares income + TDS from previous employer(s) in the same financial year
-- Enables correct TDS calculation by the new employer for the remainder of the year
(NULL, 'FORM_12B',
 '["employee_name","pan_number","financial_year","previous_employer_name","tds_deducted"]',
 '["pan_number","employee_name"]',
 '["previous_employer_tan","period_of_employment","gross_salary_band","joining_date_new_employer","assessment_year"]',
 '[["pan_number","financial_year","previous_employer_name"],["tds_deducted","assessment_year"]]',
 0.80,
 '["pdf","docx","jpeg","jpg","png"]'),

-- FORM_26AS
-- Income Tax Section 203AA: Annual TDS credit statement from TRACES portal
-- Shows all TDS deducted by all deductors (employers, banks) for a PAN in a financial year
-- Used for ITR filing verification. Raw ₹ TDS amounts → insight only.
(NULL, 'FORM_26AS',
 '["taxpayer_name","pan_number","assessment_year","deductor_name","tds_amount"]',
 '["pan_number","taxpayer_name"]',
 '["deductor_tan","deduction_date","certificate_number","form_type","acknowledgement_number","traces_download_date"]',
 '[["pan_number","assessment_year","deductor_name"],["tds_amount","certificate_number"]]',
 0.82,
 '["pdf","html","jpeg","jpg","png"]')

ON CONFLICT DO NOTHING;
