-- Migration 041: sla_policy + severity_classification_rule
--
-- prana-docs/SEVERITY_SLA_POLICY_DESIGN.md — PA-editable incident severity/SLA policy,
-- replacing hardcoded Python constants in services/incident_service.py (_SLA_MAP),
-- services/error_threshold_service.py (classification constants), services/health_service.py
-- (HEALTH_TARGETS severities), and the scattered literal severities in workflows/activities.py
-- + kafka/consumers/security_consumer.py + kafka/consumers/notif_consumer.py.
--
-- Seeded with today's real values so behavior is UNCHANGED until PA edits policy via the
-- new /admin/sla-policy and /admin/severity-rules endpoints.

CREATE TABLE IF NOT EXISTS sla_policy (
    severity              VARCHAR(2)   PRIMARY KEY,          -- P0 | P1 | P2 | P3
    sla_minutes            INTEGER      NOT NULL,
    auto_create_incident   BOOLEAN      NOT NULL DEFAULT FALSE,
    description              TEXT,
    updated_by                UUID,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO sla_policy (severity, sla_minutes, auto_create_incident, description) VALUES
    ('P0', 30,   TRUE,  'Immediate — security/DPDP breach class, PA paged'),
    ('P1', 240,  TRUE,  'Urgent — war room within 4 hours'),
    ('P2', 1440, FALSE, 'Next business day'),
    ('P3', 4320, FALSE, 'Weekly digest tier')
ON CONFLICT (severity) DO NOTHING;

-- One small rule engine, reused across all three severity-deciding domains. Evaluation
-- (see services/severity_policy_service.py): rules tried in priority order (ascending);
-- DEFAULT (match_value IS NULL) rules are a wildcard that matches any value. A PREFIX/EXACT
-- rule whose pattern matches but whose occurrence/window condition is NOT met is terminal —
-- evaluation stops with no severity (this reproduces error_threshold_service.py's original
-- "compliance path under threshold returns None, does not fall through to the novel-bug
-- check" behavior). A DEFAULT rule whose condition is not met falls through to the next rule
-- instead (novel-bug -> noise cascade). occurrence_threshold_max supports "exactly N"
-- semantics (novel-bug = exactly first occurrence) alongside occurrence_threshold's
-- "at least N" semantics (recurrence-based promotion).
CREATE TABLE IF NOT EXISTS severity_classification_rule (
    rule_id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                       VARCHAR(30)  NOT NULL,
                                  -- ERROR_OBSERVABILITY | HEALTH_CHECK | ANOMALY_RULE
    match_type                    VARCHAR(20)  NOT NULL,
                                   -- PREFIX | EXACT | DEFAULT
    match_value                    VARCHAR(200),           -- NULL when match_type = DEFAULT
    occurrence_threshold             INTEGER,                -- NULL = no lower bound
    occurrence_threshold_max          INTEGER,                -- NULL = no upper bound
    window_minutes                     INTEGER,                -- paired with the thresholds above
    severity                             VARCHAR(2)  NOT NULL,
    priority                              INTEGER     NOT NULL DEFAULT 100,  -- lower = evaluated first
    is_active                              BOOLEAN     NOT NULL DEFAULT TRUE,
    description                             TEXT,
    updated_by                               UUID,
    updated_at                                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (match_type IN ('PREFIX', 'EXACT', 'DEFAULT')),
    CHECK (match_type = 'DEFAULT' OR match_value IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_severity_rule_domain ON severity_classification_rule(domain, priority)
    WHERE is_active = TRUE;

-- domain=ERROR_OBSERVABILITY — replaces error_threshold_service.py's hardcoded constants
-- rule_id has no natural business key to ON CONFLICT against, so idempotency is a
-- per-domain "only seed if this domain has no rows yet" guard instead — safe to rerun,
-- and still lets PA delete/edit individual rows afterwards without them reappearing.
INSERT INTO severity_classification_rule
    (domain, match_type, match_value, occurrence_threshold, occurrence_threshold_max, window_minutes, severity, priority, description)
SELECT * FROM (VALUES
    ('ERROR_OBSERVABILITY', 'PREFIX', '/auth/',                 NULL::int, NULL::int, NULL::int, 'P1', 10, 'Security-critical HTTP path'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/totp/',                 NULL, NULL, NULL, 'P1', 10, 'Security-critical HTTP path'),
    ('ERROR_OBSERVABILITY', 'EXACT',  'AuthConsumer',           NULL, NULL, NULL, 'P1', 10, 'Security-critical Kafka consumer'),
    ('ERROR_OBSERVABILITY', 'EXACT',  'verify_audit_integrity', NULL, NULL, NULL, 'P1', 10, 'Security-critical Temporal activity'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/v1/dpdp/',               3, NULL,   10, 'P2', 20, 'Compliance-critical endpoint, recurring'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/v1/ingest/',             3, NULL,   10, 'P2', 20, 'Compliance-critical endpoint, recurring'),
    ('ERROR_OBSERVABILITY', 'DEFAULT', NULL,                     1,    1, NULL, 'P2', 90, 'Novel bug, first occurrence'),
    ('ERROR_OBSERVABILITY', 'DEFAULT', NULL,                    10, NULL,   15, 'P3', 95, 'Noisy recurrence, systemic breakage signal')
) AS v(domain, match_type, match_value, occurrence_threshold, occurrence_threshold_max, window_minutes, severity, priority, description)
WHERE NOT EXISTS (SELECT 1 FROM severity_classification_rule WHERE domain = 'ERROR_OBSERVABILITY');

-- domain=HEALTH_CHECK — replaces health_service.py's HEALTH_TARGETS severities
INSERT INTO severity_classification_rule
    (domain, match_type, match_value, severity, priority, description)
SELECT * FROM (VALUES
    ('HEALTH_CHECK', 'EXACT', 'prana-api', 'P1', 10, 'CPU service down — REST + Temporal'),
    ('HEALTH_CHECK', 'EXACT', 'prana-ai',  'P2', 10, 'GPU pipeline worker down'),
    ('HEALTH_CHECK', 'EXACT', 'prana-ask', 'P3', 10, 'GPU chatbot worker down')
) AS v(domain, match_type, match_value, severity, priority, description)
WHERE NOT EXISTS (SELECT 1 FROM severity_classification_rule WHERE domain = 'HEALTH_CHECK');

-- domain=ANOMALY_RULE — replaces the scattered literal "P0" in workflows/activities.py,
-- fixes the security_consumer.py (P3) vs notif_consumer.py (P2) default-severity
-- disagreement (both now resolve via the same DEFAULT row), and doubles as the tunable
-- detection threshold config for workflows/security.py's run_anomaly_detection_batch —
-- occurrence_threshold/window_minutes here ARE the detection thresholds, not just severity
-- gates. Initial values are sane starting defaults, meant to be tuned from real traffic via
-- the PA policy screen, not precision-researched numbers.
INSERT INTO severity_classification_rule
    (domain, match_type, match_value, occurrence_threshold, window_minutes, severity, priority, description)
SELECT * FROM (VALUES
    ('ANOMALY_RULE', 'EXACT', 'CROSS_TENANT_UPLOAD_ATTEMPT', NULL::int, NULL::int, 'P0', 10, 'Document upload resolved to a different tenant''s employee'),
    ('ANOMALY_RULE', 'EXACT', 'CROSS_TENANT_QUERY',          NULL, NULL, 'P0', 10, 'Blocked attempt to read another tenant''s resource by ID'),
    ('ANOMALY_RULE', 'EXACT', 'IMPOSSIBLE_TRAVEL',           NULL, NULL, 'P0', 15, 'Two logins imply travel speed exceeding plausibility'),
    ('ANOMALY_RULE', 'EXACT', 'PRIVILEGE_ESCALATION',        NULL, NULL, 'P1', 20, 'Self-escalation or jump to a higher-privilege role'),
    ('ANOMALY_RULE', 'EXACT', 'BRUTE_FORCE',                    5,   15, 'P1', 30, 'Repeated failed login attempts, same identifier'),
    ('ANOMALY_RULE', 'EXACT', 'BULK_DOC_ACCESS',                50,  10, 'P1', 30, 'Unusually high document access volume, same actor'),
    ('ANOMALY_RULE', 'EXACT', 'PRE_EXIT_BULK',                  20, 1440, 'P1', 30, 'Bulk self-access shortly before a recorded exit date'),
    ('ANOMALY_RULE', 'EXACT', 'SHARE_ENUM',                      5,   10, 'P2', 40, 'Failed OTP attempts against many distinct share tokens, same IP'),
    ('ANOMALY_RULE', 'EXACT', 'OFF_HOURS_ACCESS',              NULL, NULL, 'P2', 50, 'OA actor document access outside business hours'),
    ('ANOMALY_RULE', 'DEFAULT', NULL,                          NULL, NULL, 'P3', 99, 'Fallback for any unrecognized anomaly rule_name')
) AS v(domain, match_type, match_value, occurrence_threshold, window_minutes, severity, priority, description)
WHERE NOT EXISTS (SELECT 1 FROM severity_classification_rule WHERE domain = 'ANOMALY_RULE');

-- ROLLBACK:
-- DROP TABLE IF EXISTS severity_classification_rule;
-- DROP TABLE IF EXISTS sla_policy;
