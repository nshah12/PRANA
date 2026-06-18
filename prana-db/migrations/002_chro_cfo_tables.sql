-- Migration 002: CHRO / CFO / PA supporting tables
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: DROP TABLE IF EXISTS storage_request, insight_cache, compliance_obligation CASCADE;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('002', 'chro_cfo_tables')
ON CONFLICT (version) DO NOTHING;

-- ── Compliance obligations (CHRO calendar) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_obligation (
  obligation_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  obligation_name TEXT         NOT NULL,
  deadline        DATE         NOT NULL,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                  -- PENDING | IN_PROGRESS | COMPLETE | OVERDUE
  category        VARCHAR(50),  -- STATUTORY | REGULATORY | INTERNAL
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_tenant ON compliance_obligation(tenant_id, deadline);

-- ── Insight cache (CFO payroll aggregates — never raw ₹) ───────────────────
-- Populated nightly by InsightService / benchmark_service.
-- cache_value stores JSONB aggregates: percentiles, totals, counts — never individual figures.
CREATE TABLE IF NOT EXISTS insight_cache (
  cache_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  cache_key       TEXT         NOT NULL,
  period_month    DATE,                            -- e.g. first day of month
  payroll_total_inr BIGINT,                        -- aggregate total, not individual
  employee_count  INTEGER,
  band_label      TEXT,
  cache_value     JSONB,                           -- generic aggregated payload
  computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_insight_cache_key
  ON insight_cache(tenant_id, cache_key, period_month NULLS FIRST);
CREATE INDEX IF NOT EXISTS idx_insight_cache_tenant ON insight_cache(tenant_id, cache_key);

-- ── Storage requests (tenant → PA) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS storage_request (
  request_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  current_gb      INTEGER      NOT NULL,
  requested_gb    INTEGER      NOT NULL,
  reason          TEXT,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                  -- PENDING | APPROVED | REJECTED | ON_HOLD
  requested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  decided_by      UUID,        -- portal_admin_id
  decided_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_storage_req_status ON storage_request(status, requested_at DESC);

-- ── Add consent_status to employee_user if not present ────────────────────
ALTER TABLE employee_user
  ADD COLUMN IF NOT EXISTS consent_status VARCHAR(20) NOT NULL DEFAULT 'PENDING';
  -- PENDING | GRANTED | REVOKED

-- ── Add acknowledged_by / acknowledged_at to anomaly_event ────────────────
ALTER TABLE anomaly_event
  ADD COLUMN IF NOT EXISTS acknowledged_by  UUID;
ALTER TABLE anomaly_event
  ADD COLUMN IF NOT EXISTS acknowledged_at  TIMESTAMPTZ;
ALTER TABLE anomaly_event
  ADD COLUMN IF NOT EXISTS financial_pattern TEXT;

-- ── Add data_residency fields to tenant ───────────────────────────────────
ALTER TABLE tenant
  ADD COLUMN IF NOT EXISTS data_residency_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE tenant
  ADD COLUMN IF NOT EXISTS last_residency_check    TIMESTAMPTZ;

COMMIT;
