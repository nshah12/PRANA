-- Migration 043: document_batch table
--
-- workflows/batch_progress.py's BatchProgressWorkflow real activity implementations
-- (workflows/activities.py's write_batch_summary) already UPDATE a document_batch row
-- expecting it to exist — but no migration ever created this table and nothing ever
-- INSERTs the initial row. BatchProgressWorkflow has been live-wired since it was built
-- (WorkflowConsumer starts it on every multi-file BATCH_UPLOADED event) but every run
-- fails at the write_batch_summary activity: "relation document_batch does not exist".
--
-- routers/ingest.py's /ingest/batch handler creates the initial PROCESSING row
-- (one extra DB write alongside the per-document INSERTs already in that same request —
-- batch-summary bookkeeping for the batch this request just created, not a second
-- unrelated entity write).

CREATE TABLE IF NOT EXISTS document_batch (
    batch_id      UUID         PRIMARY KEY,
    tenant_id     UUID         NOT NULL REFERENCES tenant(tenant_id),
    total_files   INTEGER      NOT NULL DEFAULT 0,
    routed        INTEGER      NOT NULL DEFAULT 0,
    exceptions    INTEGER      NOT NULL DEFAULT 0,
    quarantined   INTEGER      NOT NULL DEFAULT 0,
    failed        INTEGER      NOT NULL DEFAULT 0,
    status        VARCHAR(20)  NOT NULL DEFAULT 'PROCESSING',
                   -- PROCESSING | COMPLETE | PARTIAL
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_document_batch_tenant ON document_batch(tenant_id, created_at DESC);

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
SELECT * FROM (VALUES
  ('pipeline_max_duration_hours', '4',  'DURATION_HOURS', 'BatchTimeoutMonitorWorkflow: per-file ceiling before a document is marked a straggler', '1', '24'),
  ('batch_max_duration_hours',    '24', 'DURATION_HOURS', 'BatchProgressWorkflow: whole-batch ceiling before remaining unfinished files are marked stragglers', '1', '168')
) AS v(config_key, config_value, value_type, description, min_value, max_value)
WHERE NOT EXISTS (
  SELECT 1 FROM platform_config WHERE platform_config.config_key = v.config_key
);

-- ROLLBACK:
-- DROP INDEX IF EXISTS idx_document_batch_tenant;
-- DROP TABLE IF EXISTS document_batch;
-- DELETE FROM platform_config WHERE config_key IN ('pipeline_max_duration_hours', 'batch_max_duration_hours');
