-- Migration 019: DPDP compliance tables + labour-law obligation enhancements
-- Adds 4 tables used by dpdp.py that were missing from schema, fixes dpdp_grievance
-- column gaps, and extends compliance_obligation for statutory labour-law tracking.
--
-- ROLLBACK: see bottom of file

-- ── 1. employee_consent — per-purpose consent records ─────────────────────────
CREATE TABLE IF NOT EXISTS employee_consent (
  consent_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  purpose           VARCHAR(50)  NOT NULL,
                    -- document_processing | insight_generation | peer_benchmark | notifications
  consent_version   VARCHAR(20)  NOT NULL DEFAULT '1.0',
  is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
  consented_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_consent_employee_purpose UNIQUE (employee_user_id, purpose)
);
CREATE INDEX IF NOT EXISTS idx_consent_employee ON employee_consent(employee_user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_consent_inactive ON employee_consent(employee_user_id)
  WHERE is_active = FALSE;

-- ── 2. erasure_request — DPDP Act S.12 right to erasure ──────────────────────
CREATE TABLE IF NOT EXISTS erasure_request (
  erasure_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  reason            TEXT,
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | CANCELLED | EXECUTING | COMPLETE
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  confirmed_at      TIMESTAMPTZ,   -- set when cooling-off window elapses with no cancel
  completed_at      TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_erasure_employee ON erasure_request(employee_user_id, status);

-- ── 3. data_export_request — DPDP Act S.11 right to access / export ──────────
CREATE TABLE IF NOT EXISTS data_export_request (
  export_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | IN_PROGRESS | READY | EXPIRED
  s3_key            TEXT,          -- populated when export package is ready
  expires_at        TIMESTAMPTZ,   -- download link TTL (platform_config.export_link_ttl_hours)
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_export_employee ON data_export_request(employee_user_id, requested_at DESC);

-- ── 4. data_correction_request — DPDP Act S.12 right to correction ───────────
CREATE TABLE IF NOT EXISTS data_correction_request (
  correction_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  field_name        VARCHAR(100) NOT NULL,
  current_value     TEXT,
  correct_value     TEXT         NOT NULL,
  evidence_note     TEXT,
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | UNDER_REVIEW | APPLIED | REJECTED
  reviewer_id       UUID         REFERENCES oa_user(oa_user_id),
  rejection_reason  TEXT,
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  resolved_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_correction_employee ON data_correction_request(employee_user_id, status);
CREATE INDEX IF NOT EXISTS idx_correction_tenant   ON data_correction_request(tenant_id, status)
  WHERE status = 'PENDING';

-- ── 5. dpdp_grievance — add missing columns to match router code ─────────────
-- Schema had pan_token + grievance_type; routers use employee_user_id + tenant_id + category.
-- Keep both: pan_token for audit-log analytics (privacy-safe); employee_user_id for auth boundary.
ALTER TABLE dpdp_grievance
  ADD COLUMN IF NOT EXISTS employee_user_id UUID REFERENCES employee_user(employee_user_id),
  ADD COLUMN IF NOT EXISTS tenant_id        UUID REFERENCES tenant(tenant_id),
  ADD COLUMN IF NOT EXISTS category         VARCHAR(50);
                            -- DATA_ACCURACY | ACCESS_DENIED | CORRECTION_REFUSED |
                            -- ERASURE_REFUSED | DATA_BREACH | NOTIFICATION | OTHER
-- Make pan_token nullable (cannot always derive it synchronously in the HTTP path)
ALTER TABLE dpdp_grievance
  ALTER COLUMN pan_token DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_grievance_employee ON dpdp_grievance(employee_user_id, raised_at DESC);
CREATE INDEX IF NOT EXISTS idx_grievance_tenant   ON dpdp_grievance(tenant_id, status);

-- ── 6. compliance_obligation — extend for statutory labour-law tracking ───────
ALTER TABLE compliance_obligation
  ADD COLUMN IF NOT EXISTS statutory_act    VARCHAR(80),
                            -- EPF_ACT | ESIC_ACT | INCOME_TAX | GRATUITY_ACT |
                            -- BONUS_ACT | MATERNITY_ACT | POSH_ACT | MIN_WAGES_ACT |
                            -- FACTORIES_ACT | SHOPS_EST_ACT | LABOUR_WELFARE_FUND
  ADD COLUMN IF NOT EXISTS period_start     DATE,
  ADD COLUMN IF NOT EXISTS period_end       DATE,
  ADD COLUMN IF NOT EXISTS filing_reference VARCHAR(100),  -- challan no. / acknowledgement
  ADD COLUMN IF NOT EXISTS submitted_by     UUID REFERENCES oa_user(oa_user_id),
  ADD COLUMN IF NOT EXISTS document_id      UUID REFERENCES document(document_id),
                            -- link to uploaded proof (ECR, Form 16 etc.)
  ADD COLUMN IF NOT EXISTS headcount        INTEGER,        -- employees covered
  ADD COLUMN IF NOT EXISTS overdue_since    DATE            -- set by StatutoryComplianceWorkflow
                            -- when deadline passed without COMPLETE status
;
CREATE INDEX IF NOT EXISTS idx_obligation_act     ON compliance_obligation(tenant_id, statutory_act, deadline);
CREATE INDEX IF NOT EXISTS idx_obligation_overdue ON compliance_obligation(tenant_id, deadline)
  WHERE status IN ('PENDING', 'OVERDUE');


-- ── ROLLBACK ─────────────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS data_correction_request;
-- DROP TABLE IF EXISTS data_export_request;
-- DROP TABLE IF EXISTS erasure_request;
-- DROP TABLE IF EXISTS employee_consent;
-- ALTER TABLE dpdp_grievance
--   DROP COLUMN IF EXISTS employee_user_id,
--   DROP COLUMN IF EXISTS tenant_id,
--   DROP COLUMN IF EXISTS category;
-- ALTER TABLE dpdp_grievance ALTER COLUMN pan_token SET NOT NULL;
-- ALTER TABLE compliance_obligation
--   DROP COLUMN IF EXISTS statutory_act,
--   DROP COLUMN IF EXISTS period_start,
--   DROP COLUMN IF EXISTS period_end,
--   DROP COLUMN IF EXISTS filing_reference,
--   DROP COLUMN IF EXISTS submitted_by,
--   DROP COLUMN IF EXISTS document_id,
--   DROP COLUMN IF EXISTS headcount,
--   DROP COLUMN IF EXISTS overdue_since;
