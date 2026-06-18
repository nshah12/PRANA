-- Migration 010: chro_report — stores generated CHRO PDF report metadata
-- Used by GET /chro/reports/{report_id} for on-demand report download.
-- report_data stores the row set as JSONB so the PDF can be regenerated
-- without re-querying the DB (useful for archived reports).

CREATE TABLE IF NOT EXISTS chro_report (
  report_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID         NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  title        TEXT         NOT NULL,
  report_type  VARCHAR(50)  NOT NULL,  -- VAULT_HEALTH | QUARTERLY | CUSTOM
  report_data  JSONB        NOT NULL,  -- {"rows": [...]}
  generated_by UUID         REFERENCES oa_user(oa_user_id),
  generated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at   TIMESTAMPTZ              -- NULL = permanent
);

CREATE INDEX IF NOT EXISTS idx_chro_report_tenant
  ON chro_report(tenant_id, generated_at DESC);

-- ROLLBACK:
-- DROP TABLE IF EXISTS chro_report;
