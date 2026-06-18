-- Migration 014: CHRO audit-grade compliance tables
-- Extends compliance_obligation with statutory metadata.
-- Adds CHRO alert config keys to platform_config so tenant_config FK is satisfied.
-- All changes are additive (safe rollback path documented below).

-- ── 1. Extend compliance_obligation with statutory fields ─────────────────────

ALTER TABLE compliance_obligation
  ADD COLUMN IF NOT EXISTS obligation_type  VARCHAR(50),
  -- FORM_16 | SALARY_SLIP | PF_FILING | ESI_FILING | TDS_QUARTERLY |
  -- GRATUITY_REVIEW | EXIT_DOCS | MATERNITY_RECORD | DPDP_CONSENT_AUDIT
  ADD COLUMN IF NOT EXISTS statutory_ref    VARCHAR(100),
  -- e.g. "IT Act 1961, S.203" | "EPF Act 1952, S.6" | "DPDP Act 2023, S.6"
  ADD COLUMN IF NOT EXISTS period           VARCHAR(20),
  -- "FY:2024-25" | "2024-Q4" | "2024-03" | "Monthly"
  ADD COLUMN IF NOT EXISTS completion_pct   INTEGER       NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_employees  INTEGER       NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS compliant_employees INTEGER    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gap_count        INTEGER       NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS notes            TEXT,
  ADD COLUMN IF NOT EXISTS last_computed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_compob_overdue
  ON compliance_obligation(tenant_id)
  WHERE status = 'OVERDUE';

CREATE INDEX IF NOT EXISTS idx_compob_type
  ON compliance_obligation(tenant_id, obligation_type)
  WHERE obligation_type IS NOT NULL;

-- ── 2. Add CHRO alert config keys to platform_config ─────────────────────────
-- tenant_config.config_key has FK → platform_config.config_key.
-- These keys must be registered here before CHROs can persist their alert prefs.

INSERT INTO platform_config (config_key, default_value, value_type, description, min_value, max_value)
VALUES
  ('chro_alert_deadline_alert',    'true',  'BOOLEAN', 'CHRO: notify when statutory deadline < 30 days away', NULL, NULL),
  ('chro_alert_vault_health_drop', 'true',  'BOOLEAN', 'CHRO: notify when org vault health drops > 5 points', NULL, NULL),
  ('chro_alert_exception_spike',   'true',  'BOOLEAN', 'CHRO: notify when exception queue exceeds 5 open', NULL, NULL),
  ('chro_alert_exit_doc_delay',    'true',  'BOOLEAN', 'CHRO: notify when exit docs not pushed within 7 days', NULL, NULL),
  ('chro_alert_security_anomaly',  'false', 'BOOLEAN', 'CHRO: notify on P0/P1 security anomaly (off by default)', NULL, NULL)
ON CONFLICT (config_key) DO NOTHING;

-- ── ROLLBACK ──────────────────────────────────────────────────────────────────
-- ALTER TABLE compliance_obligation
--   DROP COLUMN IF EXISTS obligation_type,
--   DROP COLUMN IF EXISTS statutory_ref,
--   DROP COLUMN IF EXISTS period,
--   DROP COLUMN IF EXISTS completion_pct,
--   DROP COLUMN IF EXISTS total_employees,
--   DROP COLUMN IF EXISTS compliant_employees,
--   DROP COLUMN IF EXISTS gap_count,
--   DROP COLUMN IF EXISTS notes,
--   DROP COLUMN IF EXISTS last_computed_at;
-- DROP INDEX IF EXISTS idx_compob_overdue;
-- DROP INDEX IF EXISTS idx_compob_type;
-- DELETE FROM platform_config WHERE config_key LIKE 'chro_alert_%';
