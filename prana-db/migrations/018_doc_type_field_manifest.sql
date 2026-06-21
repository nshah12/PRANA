-- Migration 018: Doc-type field manifest + unclassified document queue
--
-- PURPOSE:
--   doc_type_field_manifest — OA-Admin-configurable per-doc-type field mapping.
--     Platform-level defaults (tenant_id IS NULL) are seeded below.
--     Tenant overrides (tenant_id IS NOT NULL) shadow the platform default
--     for that tenant's pipeline runs.
--
--   unclassified_queue — Holds documents where:
--     (a) doc_type could not be determined (AUTO_DETECT found no match), OR
--     (b) required_fields were not found at sufficient confidence.
--     Distinct from exception_queue (which is identity resolution failure).
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS unclassified_queue;
--   DROP TABLE IF EXISTS doc_type_field_manifest;

-- ── Table ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS doc_type_field_manifest (
  manifest_id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

  -- NULL = platform-level default; non-NULL = tenant override
  tenant_id             UUID          REFERENCES tenant(tenant_id) ON DELETE CASCADE,

  doc_type              VARCHAR(50)   NOT NULL,
  -- Known values: SALARY_SLIP | FORM_16 | OFFER_LETTER | APPOINTMENT_LETTER |
  --               INCREMENT_LETTER | PROMOTION_LETTER | EXPERIENCE_LETTER |
  --               RELIEVING_LETTER | JOINING_LETTER | PF_ACKNOWLEDGEMENT |
  --               BANK_STATEMENT | IT_RETURN | INVESTMENT_PROOF | APPRAISAL_LETTER

  -- Fields the LLM MUST extract. Missing or low-confidence required fields
  -- trigger unclassified_queue routing.
  required_fields       JSONB         NOT NULL DEFAULT '[]',

  -- Ordered list of field names used for identity resolution.
  -- Pipeline tries index-0 first, falls back in order.
  -- Typically: ["pan_number", "employee_id", "employee_name"]
  identity_fields       JSONB         NOT NULL DEFAULT '[]',

  -- Additional fields to extract when present but not required for routing.
  optional_fields       JSONB         NOT NULL DEFAULT '[]',

  -- Combinations of field names whose co-presence identifies this doc type.
  -- Used by AUTO_DETECT scoring. Each entry is a list; ALL fields in the list
  -- must be non-null for that signal to fire.
  -- Example: [["pay_period_month", "gross_salary"], ["uan_number", "net_pay"]]
  classification_signals JSONB        NOT NULL DEFAULT '[]',

  -- Minimum overall_confidence from LLM before accepting extraction.
  -- Below this → unclassified_queue.
  confidence_threshold  FLOAT         NOT NULL DEFAULT 0.75
                        CHECK (confidence_threshold BETWEEN 0.0 AND 1.0),

  -- Supported input formats for this doc type.
  -- Pipeline rejects unsupported formats before OCR.
  -- Values: pdf | docx | jpeg | jpg | png | tiff | xlsx | auto
  supported_formats     JSONB         NOT NULL DEFAULT '["pdf","docx","jpeg","jpg","png","tiff"]',

  is_active             BOOLEAN       NOT NULL DEFAULT TRUE,

  -- Audit
  created_by            UUID          REFERENCES oa_user(oa_user_id),
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_by            UUID          REFERENCES oa_user(oa_user_id)
);

-- One platform default per doc_type (tenant_id IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_manifest_platform_doctype
  ON doc_type_field_manifest (doc_type)
  WHERE tenant_id IS NULL;

-- One tenant override per doc_type per tenant
CREATE UNIQUE INDEX IF NOT EXISTS uidx_manifest_tenant_doctype
  ON doc_type_field_manifest (tenant_id, doc_type)
  WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_manifest_tenant
  ON doc_type_field_manifest (tenant_id)
  WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_manifest_active
  ON doc_type_field_manifest (doc_type, is_active);

-- ── Unclassified queue ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS unclassified_queue (
  unclassified_id       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id           UUID          NOT NULL REFERENCES document(document_id),
  tenant_id             UUID          NOT NULL REFERENCES tenant(tenant_id),

  -- Why this document landed here
  reason                VARCHAR(50)   NOT NULL,
  -- AUTO_DETECT_NO_MATCH  — no manifest's classification_signals fired above threshold
  -- REQUIRED_FIELDS_MISSING — declared doc_type but required fields not found
  -- LOW_CONFIDENCE         — overall_confidence below manifest threshold
  -- UNSUPPORTED_FORMAT     — file format not in manifest's supported_formats
  -- FORMAT_CORRUPT         — OCR returned empty / file unreadable

  declared_doc_type     VARCHAR(50),  -- what the HRMS/OA said (NULL = AUTO_DETECT)
  best_guess_doc_type   VARCHAR(50),  -- highest-scoring AUTO_DETECT candidate (may be NULL)
  best_guess_score      FLOAT,        -- score of best_guess_doc_type (0.0–1.0)

  -- Raw OCR text stored for OA-Admin to inspect and manually classify
  -- Redacted: NIK already replaced with [NIK_REDACTED] before storage
  ocr_text_redacted     TEXT,

  -- Partial fields the LLM did find (below threshold but stored for context)
  partial_fields        JSONB         NOT NULL DEFAULT '{}',

  status                VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
  -- PENDING | RESOLVED | DISMISSED

  -- OA-Admin resolution
  resolved_doc_type     VARCHAR(50),  -- what OA-Admin decided the doc type is
  resolved_by           UUID          REFERENCES oa_user(oa_user_id),
  resolved_at           TIMESTAMPTZ,
  resolution_note       TEXT,

  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unclassified_tenant_status
  ON unclassified_queue (tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_unclassified_document
  ON unclassified_queue (document_id);

-- ── Platform-default manifests (seeded once; tenant_id IS NULL) ───────────────

INSERT INTO doc_type_field_manifest
  (tenant_id, doc_type, required_fields, identity_fields, optional_fields,
   classification_signals, confidence_threshold, supported_formats)
VALUES

-- SALARY_SLIP
(NULL, 'SALARY_SLIP',
 '["employee_name","employer_name","pay_period_month","pay_period_year","net_pay"]',
 '["pan_number","employee_id","employee_name"]',
 '["designation","department","location","gross_ctc","basic_salary","hra",
   "pf_employee","tds_amount","pf_number","uan_number"]',
 '[["pay_period_month","net_pay"],["uan_number","gross_ctc"],["pf_number","basic_salary"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- FORM_16
(NULL, 'FORM_16',
 '["employee_name","employer_name","financial_year","gross_salary","tds_deducted"]',
 '["pan_number","employee_id","employee_name"]',
 '["employer_tan","employer_pan","assessment_year","standard_deduction",
   "net_taxable_income","tax_payable"]',
 '[["financial_year","tds_deducted"],["assessment_year","gross_salary"],["employer_tan","pan_number"]]',
 0.80,
 '["pdf","jpeg","jpg","png","tiff"]'),

-- OFFER_LETTER
(NULL, 'OFFER_LETTER',
 '["employee_name","employer_name","designation","date_of_joining","ctc"]',
 '["pan_number","employee_id","employee_name"]',
 '["department","location","probation_period","notice_period","offer_date","grade","band"]',
 '[["date_of_joining","ctc"],["designation","probation_period"],["offer_date","ctc"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- APPOINTMENT_LETTER
(NULL, 'APPOINTMENT_LETTER',
 '["employee_name","employer_name","designation","date_of_joining"]',
 '["employee_id","employee_name","pan_number"]',
 '["department","location","employee_id","basic_salary","probation_period"]',
 '[["date_of_joining","designation"],["employee_id","employer_name"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- JOINING_LETTER
(NULL, 'JOINING_LETTER',
 '["employee_name","employer_name","date_of_joining","designation"]',
 '["employee_id","employee_name"]',
 '["department","location","reporting_manager","employee_id"]',
 '[["date_of_joining","employer_name"],["reporting_manager","designation"]]',
 0.72,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- INCREMENT_LETTER
(NULL, 'INCREMENT_LETTER',
 '["employee_name","employer_name","effective_date","revised_ctc"]',
 '["employee_id","employee_name","pan_number"]',
 '["designation","department","previous_ctc","increment_percentage","new_basic"]',
 '[["revised_ctc","effective_date"],["increment_percentage","effective_date"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- PROMOTION_LETTER
(NULL, 'PROMOTION_LETTER',
 '["employee_name","employer_name","effective_date","new_designation"]',
 '["employee_id","employee_name","pan_number"]',
 '["previous_designation","new_grade","new_ctc","department","location"]',
 '[["new_designation","effective_date"],["previous_designation","new_designation"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- RELIEVING_LETTER
(NULL, 'RELIEVING_LETTER',
 '["employee_name","employer_name","last_working_day"]',
 '["employee_id","employee_name","pan_number"]',
 '["designation","date_of_joining","department","reason_for_leaving","relieving_date"]',
 '[["last_working_day","employer_name"],["date_of_joining","last_working_day"]]',
 0.75,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- EXPERIENCE_LETTER
(NULL, 'EXPERIENCE_LETTER',
 '["employee_name","employer_name","date_of_joining","last_working_day"]',
 '["employee_id","employee_name"]',
 '["designation","department","tenure_years","conduct_remark"]',
 '[["date_of_joining","last_working_day"],["tenure_years","employer_name"]]',
 0.72,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- PF_ACKNOWLEDGEMENT
(NULL, 'PF_ACKNOWLEDGEMENT',
 '["employee_name","uan_number","employer_name","pf_period"]',
 '["uan_number","employee_id","employee_name"]',
 '["pf_number","employee_share","employer_share","establishment_code","member_id"]',
 '[["uan_number","pf_period"],["pf_number","employee_share"]]',
 0.78,
 '["pdf","jpeg","jpg","png","tiff"]'),

-- BANK_STATEMENT
(NULL, 'BANK_STATEMENT',
 '["account_holder_name","bank_name","account_number","statement_period"]',
 '["account_holder_name","pan_number"]',
 '["ifsc_code","branch_name","opening_balance","closing_balance","total_credit","total_debit"]',
 '[["account_number","statement_period"],["ifsc_code","bank_name"]]',
 0.78,
 '["pdf","xlsx","jpeg","jpg","png"]'),

-- IT_RETURN
(NULL, 'IT_RETURN',
 '["taxpayer_name","assessment_year","gross_total_income","tax_payable"]',
 '["pan_number","taxpayer_name"]',
 '["acknowledgement_number","filing_date","refund_amount","itr_form_type","employer_name"]',
 '[["assessment_year","gross_total_income"],["acknowledgement_number","tax_payable"]]',
 0.80,
 '["pdf","jpeg","jpg","png"]'),

-- INVESTMENT_PROOF
(NULL, 'INVESTMENT_PROOF',
 '["investor_name","investment_type","financial_year","amount"]',
 '["pan_number","investor_name"]',
 '["policy_number","fund_name","maturity_date","nominee_name","folio_number"]',
 '[["investment_type","amount","financial_year"],["policy_number","investor_name"]]',
 0.72,
 '["pdf","docx","jpeg","jpg","png","tiff"]'),

-- APPRAISAL_LETTER
(NULL, 'APPRAISAL_LETTER',
 '["employee_name","employer_name","appraisal_period","rating"]',
 '["employee_id","employee_name","pan_number"]',
 '["designation","department","kra_summary","revised_ctc","effective_date","manager_name"]',
 '[["appraisal_period","rating"],["kra_summary","revised_ctc"]]',
 0.72,
 '["pdf","docx","jpeg","jpg","png","tiff"]')

ON CONFLICT DO NOTHING;
