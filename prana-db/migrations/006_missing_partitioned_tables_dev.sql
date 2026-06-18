-- Migration 006: Create partitioned tables as plain tables for dev/test
-- In production these would be PARTITION BY RANGE with monthly partitions.
-- This migration creates non-partitioned equivalents for local development.

CREATE TABLE IF NOT EXISTS audit_event (
  event_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type     VARCHAR(40)  NOT NULL,
  actor_type     VARCHAR(30)  NOT NULL,
  actor_id       UUID         NOT NULL,
  tenant_id      UUID         REFERENCES tenant(tenant_id),
  pan_token      VARCHAR(64),
  document_id    UUID,
  event_metadata JSONB,
  ip_address     INET,
  occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_type   ON audit_event(event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor  ON audit_event(actor_type, actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_event(tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_doc    ON audit_event(document_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS anomaly_event (
  anomaly_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID         REFERENCES tenant(tenant_id),
  rule_name      VARCHAR(40)  NOT NULL,
  severity       VARCHAR(5)   NOT NULL,
  actor_id       UUID,
  event_metadata JSONB,
  status         VARCHAR(20)  DEFAULT 'OPEN',
  detected_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_anomaly_open ON anomaly_event(tenant_id, detected_at DESC);

CREATE TABLE IF NOT EXISTS kms_key_log (
  log_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID         REFERENCES tenant(tenant_id),
  key_type         VARCHAR(30)  NOT NULL,
  event_type       VARCHAR(20)  NOT NULL,
  status           VARCHAR(20)  NOT NULL,
  rotation_trigger VARCHAR(20),
  dek_rewrap_count INTEGER      DEFAULT 0,
  checked_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kms_tenant ON kms_key_log(tenant_id, checked_at DESC);
