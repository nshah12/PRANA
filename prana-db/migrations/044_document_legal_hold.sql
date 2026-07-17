-- Migration 044: document legal-hold columns
--
-- workflows/compliance.py's LegalHoldWorkflow (apply_legal_hold/release_legal_hold)
-- has been a bare stub with no backing schema — distinct from the existing
-- statutory_hold_until (migration 033), which is a KNOWN-expiry labour-law retention
-- date, not an indefinite litigation hold. LegalHoldWorkflow's own docstring is
-- explicit: "No SLA timeout — holds can be indefinite," which statutory_hold_until
-- cannot represent (it is a DATE, not a boolean flag).
--
-- Scope: a hold can be applied to a single document (document_id) or every
-- document belonging to one employee (employee_uuid) — LegalHoldWorkflow's params
-- carry whichever one is relevant to the litigation.

ALTER TABLE document
  ADD COLUMN IF NOT EXISTS legal_hold_active BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS legal_hold_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_doc_legal_hold ON document(legal_hold_active)
  WHERE legal_hold_active = TRUE;

-- ROLLBACK:
-- DROP INDEX IF EXISTS idx_doc_legal_hold;
-- ALTER TABLE document DROP COLUMN IF EXISTS legal_hold_active;
-- ALTER TABLE document DROP COLUMN IF EXISTS legal_hold_reason;
