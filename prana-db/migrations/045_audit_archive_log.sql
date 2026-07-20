-- Migration 045: audit_archive_log table
--
-- workflows/compliance.py's AuditArchivalWorkflow (archive_audit_events_batch) needs
-- to record which audit_event rows have been copied to cold S3 storage. It CANNOT
-- mark this on audit_event itself: migration 039 REVOKEs UPDATE and DELETE on
-- audit_event from prana_app_role by design (the whole point of the tamper-evidence
-- guarantee is that nothing, including the app's own normal operation, can mutate an
-- existing row). This table is INSERT-only bookkeeping the app CAN write to (new
-- tables get prana_app_role CRUD via migration 039's ALTER DEFAULT PRIVILEGES) — it
-- tracks which rows have been archived without ever touching audit_event's own rows.
-- The physical move-to-cold (partition detach on the monthly RANGE partitions) is an
-- out-of-band DBA/superuser operation, not something the app performs.

CREATE TABLE IF NOT EXISTS audit_archive_log (
  event_id     UUID         PRIMARY KEY,   -- audit_event.event_id, not a FK (never mutate audit_event)
  archived_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  s3_key       TEXT         NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_archive_log_archived_at ON audit_archive_log(archived_at);

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
SELECT * FROM (VALUES
  ('audit_archival_cutoff_days', '730', 'DURATION_DAYS',
   'AuditArchivalWorkflow: age (days) after which audit_event rows are copied to cold S3 storage. '
   'See prana-docs/KAFKA_REDIS_ARCHITECTURE.md Sec.8 for the 2-year hot-retention policy this backs.',
   '30', '2555'),
  ('audit_archival_batch_size', '5000', 'COUNT',
   'AuditArchivalWorkflow: max rows archived per activity execution.', '100', '50000')
) AS v(config_key, config_value, value_type, description, min_value, max_value)
WHERE NOT EXISTS (
  SELECT 1 FROM platform_config WHERE platform_config.config_key = v.config_key
);

-- ROLLBACK:
-- DROP INDEX IF EXISTS idx_audit_archive_log_archived_at;
-- DROP TABLE IF EXISTS audit_archive_log;
-- DELETE FROM platform_config WHERE config_key IN ('audit_archival_cutoff_days', 'audit_archival_batch_size');
