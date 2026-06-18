-- Migration 013: HRMS Connector Credential Storage
-- Uses existing envelope encryption pattern (same as EPFO creds in tenant_config).
-- enc_credentials = KMS_Encrypt(JSON{client_id, client_secret, api_key, ...}, tenant_KEK)
-- tenant_id is the isolation boundary — identical to every other tenant-scoped table.

CREATE TABLE IF NOT EXISTS hrms_connector_config (
  connector_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id),
  connector_type    VARCHAR(30)  NOT NULL,
                    -- 'darwinbox' | 'keka' | 'sap_sf' | 'workday' | 'zoho_people' |
                    -- 'greythr' | 'peoplestrong' | 'oracle_hcm' | 'spine_hr' | 'beehive' |
                    -- 'sftp' | 'sharepoint' | 'gdrive' | 'azure_blob' | 's3' | 'custom'
  integration_mode  VARCHAR(20)  NOT NULL DEFAULT 'PULL',
                    -- 'PULL' | 'PUSH' | 'WEBHOOK' | 'SHARED_LOCATION'
  display_name      VARCHAR(100) NOT NULL,
  enc_credentials   BYTEA        NOT NULL,   -- KMS-encrypted JSON blob, tenant KEK
  kek_arn           TEXT         NOT NULL,   -- KMS key ARN used to encrypt (needed for decrypt)
  last_pulled_at    TIMESTAMPTZ,             -- Delta cursor for Pull mode
  pull_schedule     VARCHAR(50),             -- Cron expression, NULL = use platform default
  status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                    -- 'ACTIVE' | 'PAUSED' | 'REVOKED'
  created_by        UUID         REFERENCES oa_user(oa_user_id),
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hrms_conn_tenant ON hrms_connector_config(tenant_id) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_hrms_conn_type   ON hrms_connector_config(tenant_id, connector_type);

-- ROLLBACK:
-- DROP TABLE IF EXISTS hrms_connector_config;
