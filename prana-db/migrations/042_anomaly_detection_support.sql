-- Migration 042: anomaly-detection support
--
-- prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3 — schema additions needed to implement
-- workflows/security.py's previously-stub run_anomaly_detection_batch for real, and to
-- seed config for the anomaly-detection rules and policy-lock activities.
--
-- Detection THRESHOLDS (occurrence count + window) for count-shaped rules (BULK_DOC_ACCESS,
-- BRUTE_FORCE, SHARE_ENUM, PRE_EXIT_BULK) deliberately live in severity_classification_rule
-- (migration 041), not here — one screen (PA's Classification Rules tab), one mental model,
-- not two places to edit the same number. This migration only adds config that doesn't fit
-- that shape: a time-of-day window, a speed threshold, lock-behavior toggles, and a schedule
-- cadence that already existed as an unseeded reference in workflows/security.py.

-- SHARE_ENUM signal — no record of a failed share-link OTP attempt existed anywhere before
-- this (verified: share_access.py's verify-otp endpoint wrote nothing on mismatch).
CREATE TABLE share_otp_attempt (
    attempt_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id       UUID         NOT NULL REFERENCES share_token(token_id),
    ip_address     INET         NOT NULL,
    success        BOOLEAN      NOT NULL,
    attempted_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_share_otp_attempt_ip    ON share_otp_attempt(ip_address, attempted_at DESC);
CREATE INDEX idx_share_otp_attempt_token ON share_otp_attempt(token_id, attempted_at DESC);

-- PRE_EXIT_BULK lookahead — employee_master.dol already holds a (possibly future) exit date;
-- this index makes "employees exiting soon" a fast scan instead of a full table scan.
CREATE INDEX idx_em_tenant_dol ON employee_master(tenant_id, dol) WHERE dol IS NOT NULL;

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value) VALUES
  ('off_hours_start_hour',          '22',  'INTEGER',           'OFF_HOURS_ACCESS: start of after-hours window, IST 24h clock', '0', '23'),
  ('off_hours_end_hour',            '6',   'INTEGER',           'OFF_HOURS_ACCESS: end of after-hours window, IST 24h clock', '0', '23'),
  ('impossible_travel_speed_kmh',   '900', 'INTEGER',           'IMPOSSIBLE_TRAVEL: speed above which two logins are implausible (roughly commercial flight speed)', '200', '5000'),
  ('pre_exit_bulk_lookahead_days',  '30',  'DURATION_DAYS',     'PRE_EXIT_BULK: how far in advance a recorded exit date (employee_master.dol) counts as "upcoming"', '1', '90'),
  ('bulk_access_auto_lock_enabled', 'false', 'BOOLEAN',         'Auto-lock the account on a BULK_DOC_ACCESS anomaly — ships OFF, PA opt-in after trusting real thresholds', 'false', 'true'),
  ('brute_force_auto_lock_enabled', 'false', 'BOOLEAN',         'Auto-lock the account on a BRUTE_FORCE anomaly — ships OFF, PA opt-in after trusting real thresholds', 'false', 'true'),
  ('policy_lock_default_hours',     '24',  'DURATION_HOURS',    'PolicyLockWorkflow default lock duration when auto-lock is enabled', '1', '168'),
  ('platform_anomaly_check_minutes','5',   'DURATION_MINUTES',  'AnomalyDetectionWorkflow batch-scan interval — was referenced but never seeded before this migration', '1', '60')
ON CONFLICT (config_key) DO NOTHING;

-- ROLLBACK:
-- DELETE FROM platform_config WHERE config_key IN (
--   'off_hours_start_hour', 'off_hours_end_hour', 'impossible_travel_speed_kmh',
--   'pre_exit_bulk_lookahead_days', 'bulk_access_auto_lock_enabled',
--   'brute_force_auto_lock_enabled', 'policy_lock_default_hours', 'platform_anomaly_check_minutes'
-- );
-- DROP INDEX IF EXISTS idx_em_tenant_dol;
-- DROP TABLE IF EXISTS share_otp_attempt;
