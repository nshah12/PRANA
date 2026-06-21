-- Migration 017: notification_log + incident tables
-- notification_log: every outbound notification with delivery tracking
-- incident: P0/P1 security anomalies, SLA breaches, DPDP grievances

CREATE TABLE IF NOT EXISTS notification_log (
    notification_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID         REFERENCES tenant(tenant_id),         -- NULL for platform-level notifs
    event_type       VARCHAR(40)  NOT NULL,                              -- ANOMALY_DETECTED, DOC_ROUTED …
    source_id        UUID,                                               -- FK to anomaly_event / audit_event / etc.
    source_table     VARCHAR(40),                                        -- which table source_id refers to
    recipient_id     UUID         NOT NULL,                              -- oa_user_id / employee_user_id / portal_admin_id
    recipient_type   VARCHAR(20)  NOT NULL,                              -- OA_USER / EMPLOYEE / PORTAL_ADMIN
    recipient_email  TEXT,
    recipient_phone  TEXT,
    channel          VARCHAR(20)  NOT NULL,                              -- EMAIL / SMS / WHATSAPP / PUSH / PORTAL_BELL
    template_id      VARCHAR(50)  NOT NULL,
    template_data    JSONB,                                              -- variables substituted (no PII)
    status           VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',             -- QUEUED / SENT / FAILED / BOUNCED / SUPPRESSED
    provider_ref     TEXT,                                               -- SES message_id / MSG91 ref
    sent_at          TIMESTAMPTZ,
    failed_at        TIMESTAMPTZ,
    error_message    TEXT,
    retry_count      SMALLINT     NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_log_tenant_created  ON notification_log (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_log_recipient       ON notification_log (recipient_id, channel, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_log_queued_failed   ON notification_log (status) WHERE status IN ('QUEUED', 'FAILED');
CREATE INDEX IF NOT EXISTS idx_notif_log_event_type      ON notification_log (event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS incident (
    incident_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID         REFERENCES tenant(tenant_id),          -- NULL for platform incidents
    incident_type    VARCHAR(40)  NOT NULL,                               -- SECURITY_ANOMALY / SLA_BREACH / DPDP_GRIEVANCE / PLATFORM_HEALTH
    severity         VARCHAR(5)   NOT NULL,                               -- P0 / P1 / P2 / P3
    title            TEXT         NOT NULL,
    description      TEXT,
    source_table     VARCHAR(40),                                         -- anomaly_event / exception_queue / dpdp_grievance
    source_id        UUID,
    assigned_to      UUID,                                                -- oa_user_id or portal_admin_id
    assigned_role    VARCHAR(20),                                         -- CISO / OA_ADMIN / PA / GRIEVANCE_OFFICER
    status           VARCHAR(20)  NOT NULL DEFAULT 'OPEN',                -- OPEN / IN_PROGRESS / RESOLVED / ESCALATED
    sla_deadline     TIMESTAMPTZ,
    escalated_at     TIMESTAMPTZ,
    resolved_at      TIMESTAMPTZ,
    resolved_by      UUID,
    resolution_note  TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_tenant_status    ON incident (tenant_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_incident_sla              ON incident (sla_deadline) WHERE status != 'RESOLVED';
CREATE INDEX IF NOT EXISTS idx_incident_open_severity    ON incident (severity, created_at DESC) WHERE status = 'OPEN';

-- ROLLBACK:
-- DROP TABLE IF EXISTS incident;
-- DROP TABLE IF EXISTS notification_log;
