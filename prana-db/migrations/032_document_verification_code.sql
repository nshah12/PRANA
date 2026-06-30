-- Migration 032 — document verification code
-- Adds a short, unique, human-readable code to every ROUTED document.
-- Used by GET /public/verify/{code} for recruiter / bank credential verification.
-- Generated on ROUTED transition in internal_pipeline.py — NULL until document is ROUTED.

ALTER TABLE document
  ADD COLUMN IF NOT EXISTS verification_code VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_verification_code
  ON document(verification_code)
  WHERE verification_code IS NOT NULL;
