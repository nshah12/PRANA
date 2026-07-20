-- 047_employee_insight.sql
-- employee_insight — per-employee LLM-derived insight storage, one row per
-- (employee_uuid, insight_type). Referenced by name in workflows/intelligence.py's
-- CareerInsightWorkflow and SkillGapWorkflow docstrings but never actually
-- created. insights is JSONB and, per the platform privacy contract, must never
-- contain raw ₹ figures, PAN, or NIK — insight_type disambiguates which workflow
-- wrote a given row (market_comp insights also land here, same shape).

CREATE TABLE IF NOT EXISTS employee_insight (
  insight_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_uuid UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  tenant_id     UUID         REFERENCES tenant(tenant_id),
  insight_type  VARCHAR(20)  NOT NULL CHECK (insight_type IN ('CAREER', 'SKILL_GAP', 'MARKET_COMP')),
  insights      JSONB        NOT NULL DEFAULT '{}',
  computed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_insight_type ON employee_insight(employee_uuid, insight_type);

-- ROLLBACK:
-- DROP INDEX IF EXISTS idx_employee_insight_type;
-- DROP TABLE IF EXISTS employee_insight;
