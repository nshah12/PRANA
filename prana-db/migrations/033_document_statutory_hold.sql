-- 033_document_statutory_hold.sql
-- Adds statutory retention columns to document table.
-- These support DPDP Act erasure requests that conflict with Indian labour law retention
-- obligations (EPF Act, Income Tax Act, Companies Act, Gratuity Act).
-- employee_visible=FALSE hides a document from the employee vault without deleting it.
-- employer_visible=FALSE is set only when the full physical delete runs after hold expiry.

ALTER TABLE document
  ADD COLUMN statutory_hold_reason VARCHAR(50),
  ADD COLUMN statutory_hold_until  DATE,
  ADD COLUMN statutory_hold_set_at TIMESTAMPTZ,
  ADD COLUMN statutory_hold_set_by VARCHAR(50),
  ADD COLUMN employee_visible      BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN employer_visible      BOOLEAN NOT NULL DEFAULT TRUE;

-- statutory_hold_set_by values:
--   'SYSTEM_INFER'  — set automatically by doc_type at ingest time
--   <oa_user_id>    — set manually by OA-Admin or CISO (override)

-- Index for RetentionWorkflow timer queries: find documents whose hold has expired
CREATE INDEX idx_doc_statutory_hold
  ON document (statutory_hold_until)
  WHERE statutory_hold_until IS NOT NULL
    AND is_deleted = FALSE
    AND employer_visible = TRUE;
