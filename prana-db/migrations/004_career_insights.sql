-- Migration 004: Career insights — career_event insight columns + salary_band table
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: ALTER TABLE career_event DROP COLUMN IF EXISTS insight_text,
--                                    DROP COLUMN IF EXISTS insight_generated_at,
--                                    DROP COLUMN IF EXISTS insight_model_version;
--           DROP TABLE IF EXISTS salary_band CASCADE;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('004', 'career_insights')
ON CONFLICT (version) DO NOTHING;

-- ── Insight columns on career_event ────────────────────────────────────────────
-- insight_text: LLM-generated career narrative (benchmarks/percentiles only — no raw ₹)
--   Also embedded into Qdrant collection employee_{uuid} by InsightRefreshWorkflow.
-- insight_generated_at: timestamp of last insight generation (used for staleness checks)
-- insight_model_version: model tag at generation time (for auditability)

ALTER TABLE career_event
  ADD COLUMN IF NOT EXISTS insight_text           TEXT,
  ADD COLUMN IF NOT EXISTS insight_generated_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS insight_model_version  VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_career_event_insight_stale
  ON career_event(insight_generated_at NULLS FIRST)
  WHERE insight_text IS NULL OR insight_generated_at IS NULL;

-- ── salary_band — benchmark percentile bands per role/industry ─────────────────
-- Populated by AnalyticsService / BatchBenchmarkWorkflow.
-- Used by benchmark_service.py (the privacy boundary): raw ₹ → percentile label.
-- NEVER store individual employee salaries here — only aggregated cohort bands.
-- Minimum cohort size enforced at read time (CFO_COHORT_MIN = 30).

CREATE TABLE IF NOT EXISTS salary_band (
  band_id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID         REFERENCES tenant(tenant_id) ON DELETE CASCADE,
                       -- NULL = platform-wide band (cross-tenant anonymised)
  doc_type            VARCHAR(40)  NOT NULL,  -- SALARY_SLIP | FORM_16 | etc.
  role_normalised     VARCHAR(200) NOT NULL,  -- e.g. "Software Engineer L3"
  industry            VARCHAR(100),
  location_tier       VARCHAR(10),            -- T1 | T2 | T3
  period_year         SMALLINT     NOT NULL,
  period_month        SMALLINT,               -- NULL = annual band
  p25_index           NUMERIC(6,2) NOT NULL,  -- 25th percentile (indexed, not raw ₹)
  p50_index           NUMERIC(6,2) NOT NULL,
  p75_index           NUMERIC(6,2) NOT NULL,
  p90_index           NUMERIC(6,2) NOT NULL,
  cohort_size         INTEGER      NOT NULL CHECK (cohort_size >= 30),
  computed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_salary_band UNIQUE (tenant_id, doc_type, role_normalised, period_year, period_month, location_tier)
);

CREATE INDEX IF NOT EXISTS idx_salary_band_lookup
  ON salary_band(doc_type, role_normalised, period_year)
  WHERE cohort_size >= 30;

COMMIT;
