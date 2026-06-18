-- Migration 005: Performance indexes for vault activity feed + audit queries
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: DROP INDEX IF EXISTS idx_dal_employee_occurred;
--           DROP INDEX IF EXISTS idx_doc_employee_pushed;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('005', 'document_access_log_index')
ON CONFLICT (version) DO NOTHING;

-- Fast reverse-chronological access log per employee (GET /vault/activity)
CREATE INDEX IF NOT EXISTS idx_dal_employee_occurred
  ON document_access_log(employee_user_id, occurred_at DESC);

-- Fast document list per employee ordered by ingest time (pipeline inbox)
CREATE INDEX IF NOT EXISTS idx_doc_employee_pushed
  ON document(employee_user_id, pushed_at DESC)
  WHERE status != 'DELETED';

COMMIT;
