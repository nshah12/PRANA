-- Migration 024: Comp Benchmarking — opt-in data collection + k-anonymous cohort results
-- salary_band table already exists (schema.sql:838) — this adds the opt-in + result layers.

-- Employee opt-in to contribute their comp data to anonymous benchmarks.
-- Separate from peer_benchmark consent in employee_consent (purpose='peer_benchmark').
-- This table tracks WHAT dimension they contributed to (cohort key) for audit purposes.
CREATE TABLE IF NOT EXISTS comp_contribution (
  contribution_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  pan_token         VARCHAR(64)  NOT NULL,           -- links to employee_master without PAN exposure
  cohort_key        VARCHAR(300) NOT NULL,
  -- cohort_key = designation_slug|industry|city|experience_band
  -- e.g. "senior-engineer|fintech|bengaluru|5-7y"
  -- Never stores raw salary — that lives only in salary_band aggregates
  contributed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  withdrawn_at      TIMESTAMPTZ,                     -- NULL = still contributing
  CONSTRAINT uq_contribution_employee_cohort UNIQUE (employee_user_id, cohort_key)
);
CREATE INDEX idx_contrib_cohort   ON comp_contribution(cohort_key) WHERE withdrawn_at IS NULL;
CREATE INDEX idx_contrib_employee ON comp_contribution(employee_user_id);

-- Peer benchmark result per employee (what percentile THEY are in their cohort).
-- Rebuilt by PeerBenchmarkWorkflow whenever cohort crosses k=50 threshold.
-- No raw salary stored — only percentile label and suppression flag.
CREATE TABLE IF NOT EXISTS peer_benchmark_result (
  result_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  cohort_key        VARCHAR(300) NOT NULL,
  percentile_band   VARCHAR(20),
  -- 'P10-P25' | 'P25-P40' | 'P40-P60' | 'P60-P75' | 'P75-P90' | 'P90+'
  cohort_size       INTEGER      NOT NULL,           -- must be >= 50 to publish
  suppressed        BOOLEAN      NOT NULL DEFAULT FALSE,
  -- TRUE if cohort_size < 50 — result hidden, "not enough data yet" shown
  label_text        VARCHAR(200),
  -- Human-readable: "Your comp is in the top 25% for Senior Engineers in Fintech, Bengaluru"
  computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_benchmark_employee_cohort UNIQUE (employee_user_id, cohort_key)
);
CREATE INDEX idx_benchmark_employee ON peer_benchmark_result(employee_user_id);

-- CHRO comp intelligence view: how does their org's grade structure compare to market?
-- Rebuilt nightly per tenant by CompBandRefreshWorkflow.
-- salary_band table (existing) stores the cross-tenant medians.
-- This view joins the two for the CHRO dashboard query.
CREATE OR REPLACE VIEW chro_comp_intelligence AS
SELECT
  sb.tenant_id,
  sb.grade,
  sb.department,
  sb.period,
  sb.sample_count,
  sb.p25,
  sb.p50,
  sb.p75,
  sb.computed_at,
  CASE WHEN sb.sample_count < 50 THEN TRUE ELSE FALSE END AS suppressed
FROM salary_band sb
WHERE sb.tenant_id IS NOT NULL;

COMMENT ON TABLE comp_contribution IS
  'Employee opt-in to contribute anonymised comp data to cohort benchmarks. No raw salary stored.';
COMMENT ON TABLE peer_benchmark_result IS
  'Per-employee percentile band — rebuilt when cohort crosses k=50. Suppressed below threshold.';
