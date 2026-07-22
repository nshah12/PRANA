-- Migration 040: error_event
--
-- 4th track of the incident system (prana-docs/ERROR_OBSERVABILITY_DESIGN.md,
-- approved 2026-07-15): captures every caught/uncaught application exception
-- (HTTP handlers, Kafka consumers, Temporal activities) that previously had
-- zero durable trace anywhere. Deduplicated by fingerprint — one row per
-- distinct bug, incremented on repeat, not one row per occurrence.
--
-- NOTE: like `incident` and `notification_log` (migration 017), this table is
-- migration-only and intentionally not folded into schema.sql, since its FK
-- target `incident` is itself migration-only — schema.sql is not currently
-- "deployable from scratch" for the full incident system (a pre-existing gap,
-- not introduced or fixed by this migration).

CREATE TABLE IF NOT EXISTS error_event (
    error_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint         VARCHAR(64)  NOT NULL,   -- sha256(exception_type + top_frame_location + normalized_message)
    exception_type      VARCHAR(200) NOT NULL,   -- e.g. "RuntimeError", "asyncpg.UniqueViolationError"
    message             TEXT,                    -- str(exc), truncated + PII-scrubbed
    traceback           TEXT,                    -- traceback.format_exc() text — frames/lines only, never local vars
    source              VARCHAR(30)  NOT NULL,    -- HTTP | KAFKA_CONSUMER | TEMPORAL_ACTIVITY
    source_detail       VARCHAR(200),             -- route path, consumer class name, or activity name
    request_id          UUID,                     -- correlates to the HTTP request; NULL for consumer/activity errors
    event_id            UUID,                     -- correlates to the Kafka event (consumer errors only)
    tenant_id           UUID         REFERENCES tenant(tenant_id),   -- NULL for platform-level errors
    actor_type          VARCHAR(30),
    actor_id            UUID,
    occurrence_count    INTEGER      NOT NULL DEFAULT 1,
    first_seen_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status               VARCHAR(20)  NOT NULL DEFAULT 'NEW',
                          -- NEW | ACKNOWLEDGED | RESOLVED | IGNORED
    linked_incident_id  UUID         REFERENCES incident(incident_id),
    resolved_by         UUID,
    resolved_at         TIMESTAMPTZ,
    resolution_note     TEXT
);

-- One open row per fingerprint (dedup); a resolved fingerprint can recur as a fresh row.
CREATE UNIQUE INDEX IF NOT EXISTS idx_error_event_fingerprint_open ON error_event(fingerprint)
    WHERE status IN ('NEW', 'ACKNOWLEDGED');
CREATE INDEX IF NOT EXISTS idx_error_event_last_seen ON error_event(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_event_tenant ON error_event(tenant_id, last_seen_at DESC)
    WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_error_event_status ON error_event(status, last_seen_at DESC);

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
VALUES (
    'error_event_retention_days', '90', 'DURATION_DAYS',
    'How long error_event rows are kept before purge — operational/debugging data, not a compliance audit trail',
    '30', '365'
)
ON CONFLICT (config_key) DO NOTHING;

-- ErrorThresholdEvaluationWorkflow schedule cadence (Pattern 3, secops-queue) —
-- see prana-docs/ERROR_OBSERVABILITY_DESIGN.md §5.
INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
VALUES (
    'error_threshold_check_interval_minutes', '15', 'DURATION_MINUTES',
    'How often ErrorThresholdEvaluationWorkflow scans open error_event rows for incident promotion',
    '5', '60'
)
ON CONFLICT (config_key) DO NOTHING;

-- ROLLBACK:
-- DELETE FROM platform_config WHERE config_key = 'error_threshold_check_interval_minutes';
-- DELETE FROM platform_config WHERE config_key = 'error_event_retention_days';
-- DROP TABLE IF EXISTS error_event;
