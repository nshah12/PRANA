-- Migration 031: add error_code to audit_event
--
-- Stores the PranaError / PipelineError / AskError code for failure events.
-- Nullable: success events (no error) leave it NULL.
-- Max 64 chars covers the longest pipeline error code (S04_EXTRACT_OCR_TEXTRACT_UNAVAILABLE = 38).
--
-- Consumer: AuditConsumer writes error_code when the Kafka event carries one.
-- Query pattern: WHERE error_code = 'INVALID_TOTP' AND occurred_at > NOW() - INTERVAL '24 hours'
--   → ops can alert on error spikes without full-text scanning the event_metadata JSONB.

ALTER TABLE audit_event
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(64);

-- Partial index: only index rows that have an error code (NULL rows skipped).
CREATE INDEX IF NOT EXISTS idx_audit_event_error_code
    ON audit_event (error_code, occurred_at DESC)
    WHERE error_code IS NOT NULL;

COMMENT ON COLUMN audit_event.error_code IS
    'Structured error code (PranaError / PipelineError / AskError). NULL on success events.';
