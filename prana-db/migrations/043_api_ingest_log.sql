-- Migration 043: api_ingest_log
--
-- IntegrationConsumer._handle_hrms_failure (kafka/consumers/integration_consumer.py,
-- prana.integrations.events → HRMS_WEBHOOK_FAILED) has queried and updated this table
-- since it was written, but the table was never created anywhere — the first real
-- HRMS_WEBHOOK_FAILED event against a real DB raised asyncpg.UndefinedTableError.
-- Existing tests never caught this because they mock conn.fetchrow directly instead
-- of exercising a real schema.
--
-- One row per ingest request that has hit at least one retryable failure. The row is
-- created by the consumer itself (via INSERT ... ON CONFLICT) on the first failure —
-- not proactively by the HTTP handler in routers/ingest.py, which is bound by the
-- HTTP handler contract (validate → S3 put → 1 DB write → 1 Kafka publish → 202,
-- KAFKA_REDIS_ARCHITECTURE.md §4) and already spends its one DB write on the
-- `document` INSERT.

CREATE TABLE IF NOT EXISTS api_ingest_log (
  request_id     UUID         PRIMARY KEY,
  tenant_id      UUID         NOT NULL REFERENCES tenant(tenant_id),
  filename       TEXT,
  reason         TEXT,
  retry_count    SMALLINT     NOT NULL DEFAULT 0,
  last_retry_at  TIMESTAMPTZ,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_ingest_log_tenant ON api_ingest_log(tenant_id, created_at DESC);

-- ROLLBACK:
-- DROP TABLE IF EXISTS api_ingest_log;
