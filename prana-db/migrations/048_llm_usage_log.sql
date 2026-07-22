-- Migration 048: llm_usage_log — token/cost tracking for the PA Meta Dashboard's
-- LLM Usage tile. prana-ai writes directly via its own asyncpg pool (same
-- YugabyteDB cluster, no cross-service Python import — see
-- .claude/rules/deployment.md, which only forbids Python imports, not shared
-- DB access).
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: DROP TABLE IF EXISTS llm_usage_log;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('048', 'llm_usage_log')
ON CONFLICT (version) DO NOTHING;

CREATE TABLE IF NOT EXISTS llm_usage_log (
  usage_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  model              VARCHAR(100) NOT NULL,
  prompt_tokens      INTEGER      NOT NULL DEFAULT 0,
  completion_tokens  INTEGER      NOT NULL DEFAULT 0,
  total_tokens       INTEGER      NOT NULL DEFAULT 0,
  occurred_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_occurred ON llm_usage_log(occurred_at DESC);

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
VALUES ('llm_cost_per_1k_tokens_inr', '0.85', 'STRING',
        'Estimated cost (INR) per 1,000 LLM tokens, for the PA Meta Dashboard LLM Usage tile',
        NULL, NULL)
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
