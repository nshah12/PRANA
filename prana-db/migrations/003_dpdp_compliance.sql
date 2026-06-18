-- Migration 003: DPDP compliance — grievance table + consent audit columns
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: DROP TABLE IF EXISTS dpdp_grievance CASCADE;
--           ALTER TABLE employee_user DROP COLUMN IF EXISTS consent_version,
--                                     DROP COLUMN IF EXISTS consent_granted_at,
--                                     DROP COLUMN IF EXISTS consent_withdrawn_at;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('003', 'dpdp_compliance')
ON CONFLICT (version) DO NOTHING;

-- ── DPDP grievance table ───────────────────────────────────────────────────────
-- Tracks employee grievance filings under DPDP Act 2023, Section 13.
-- Lifecycle: OPEN → (optionally) ESCALATED → CLOSED
-- SLA: 30 calendar days from open to close (enforced by GrievanceWorkflow).

CREATE TABLE IF NOT EXISTS dpdp_grievance (
  grievance_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id    UUID         NOT NULL REFERENCES employee_user(employee_user_id) ON DELETE CASCADE,
  tenant_id           UUID         NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  category            VARCHAR(50)  NOT NULL,
    -- ERASURE_DELAY | CONSENT_BREACH | WRONG_DATA | EXPORT_DELAY | OTHER
  description         TEXT         NOT NULL,
  status              VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    -- OPEN | ESCALATED | CLOSED
  escalation_reason   TEXT,
  resolution_note     TEXT,
  opened_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  escalated_at        TIMESTAMPTZ,
  closed_at           TIMESTAMPTZ,
  CONSTRAINT chk_grievance_status CHECK (status IN ('OPEN', 'ESCALATED', 'CLOSED')),
  CONSTRAINT chk_grievance_category CHECK (
    category IN ('ERASURE_DELAY', 'CONSENT_BREACH', 'WRONG_DATA', 'EXPORT_DELAY', 'OTHER')
  )
);

CREATE INDEX IF NOT EXISTS idx_grievance_employee   ON dpdp_grievance(employee_user_id);
CREATE INDEX IF NOT EXISTS idx_grievance_tenant     ON dpdp_grievance(tenant_id);
CREATE INDEX IF NOT EXISTS idx_grievance_status     ON dpdp_grievance(status) WHERE status != 'CLOSED';
CREATE INDEX IF NOT EXISTS idx_grievance_opened_at  ON dpdp_grievance(opened_at DESC);

-- ── Consent audit columns on employee_user ─────────────────────────────────────
-- Tracks which version of DPDP consent the employee agreed to and when.
-- consent_withdrawn_at is set by ConsentRebumpWorkflow / explicit withdraw action.
-- Re-granting consent clears consent_withdrawn_at and updates consent_granted_at.

ALTER TABLE employee_user
  ADD COLUMN IF NOT EXISTS consent_version        VARCHAR(10)  DEFAULT 'DPDP_v1',
  ADD COLUMN IF NOT EXISTS consent_granted_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS consent_withdrawn_at   TIMESTAMPTZ;

-- Back-fill: all existing ACTIVE users are assumed to have granted consent
-- (they passed the consent screen during activation).
UPDATE employee_user
  SET consent_granted_at = activated_at,
      consent_version     = 'DPDP_v1'
WHERE status = 'ACTIVE'
  AND consent_granted_at IS NULL
  AND activated_at IS NOT NULL;

COMMIT;
