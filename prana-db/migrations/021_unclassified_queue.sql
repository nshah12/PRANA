-- Migration 021: unclassified_queue table
-- Documents whose doc_type could not be determined by Stage04 AUTO_DETECT.
-- OA-Admin resolves via POST /v1/admin/documents/{id}/classify → re-enters pipeline.
-- Referenced by: prana-ai/routers/pipeline.py write_unclassified()

BEGIN;

CREATE TABLE IF NOT EXISTS unclassified_queue (
  document_id          UUID         PRIMARY KEY REFERENCES document(document_id),
  tenant_id            UUID         NOT NULL REFERENCES tenant(tenant_id),
  reason               TEXT         NOT NULL,
    -- AUTO_DETECT_FAILED | LOW_CONFIDENCE | CONFLICTING_SIGNALS | OCR_POOR_QUALITY
  declared_doc_type    VARCHAR(50),  -- doc_type asserted by HRMS on push (may be null for SELF_UPLOAD)
  best_guess_doc_type  VARCHAR(50),  -- highest-scoring candidate from Stage04 probe (may be null)
  best_guess_score     NUMERIC(5,4), -- confidence score of best_guess (0.0000–1.0000)
  partial_fields       JSONB        NOT NULL DEFAULT '{}',
    -- extracted fields at time of failure (no raw ₹ amounts — _SENSITIVE_FIELDS stripped)
  status               VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    -- PENDING | RESOLVED | EXPIRED
  resolved_by          UUID         REFERENCES oa_user(oa_user_id),
  resolved_doc_type    VARCHAR(50),  -- doc_type selected by OA-Admin on resolution
  resolved_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unclassified_tenant
  ON unclassified_queue(tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_unclassified_pending
  ON unclassified_queue(tenant_id, created_at DESC)
  WHERE status = 'PENDING';

COMMIT;

-- ROLLBACK:
-- BEGIN;
-- DROP INDEX IF EXISTS idx_unclassified_pending;
-- DROP INDEX IF EXISTS idx_unclassified_tenant;
-- DROP TABLE IF EXISTS unclassified_queue;
-- COMMIT;
