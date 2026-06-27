-- Migration 029: HRMS Connector Definition (PA factory) + sync log
-- Adds PA-level connector catalogue + sync audit trail.
-- hrms_connector_config (tenant-level) already exists from migration 013;
-- this migration adds the factory table it should reference, plus field_mapping.
--
-- ROLLBACK:
--   ALTER TABLE hrms_connector_config DROP COLUMN IF EXISTS connector_definition_id;
--   ALTER TABLE hrms_connector_config DROP COLUMN IF EXISTS field_mapping;
--   DROP TABLE IF EXISTS hrms_sync_log;
--   DROP TABLE IF EXISTS hrms_connector_definition;

-- ── PA factory: which connectors the platform supports ───────────────────────

CREATE TABLE IF NOT EXISTS hrms_connector_definition (
  connector_definition_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_key            VARCHAR(30)  NOT NULL UNIQUE,
                           -- 'darwinbox' | 'keka' | 'sap_sf' | 'workday' |
                           -- 'zoho_people' | 'greythr' | 'peoplestrong'
  display_name             VARCHAR(100) NOT NULL,
  logo_url                 TEXT,
  auth_method              VARCHAR(20)  NOT NULL,
                           -- 'OAUTH2' | 'API_KEY' | 'WEBHOOK' | 'SFTP'
  supported_modes          TEXT[]       NOT NULL DEFAULT ARRAY['PULL'],
                           -- subset of: PULL | PUSH | WEBHOOK | SHARED_LOCATION
  canonical_field_schema   JSONB        NOT NULL DEFAULT '{}',
                           -- defines expected field→column mapping for this HRMS
  docs_url                 TEXT,
  is_active                BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hrms_def_key    ON hrms_connector_definition(connector_key);
CREATE INDEX IF NOT EXISTS idx_hrms_def_active ON hrms_connector_definition(is_active);

-- ── Tenant config: add FK to definition + tenant field-mapping overrides ─────

ALTER TABLE hrms_connector_config
  ADD COLUMN IF NOT EXISTS connector_definition_id UUID
    REFERENCES hrms_connector_definition(connector_definition_id),
  ADD COLUMN IF NOT EXISTS field_mapping JSONB NOT NULL DEFAULT '{}';
                           -- tenant-specific overrides on top of canonical_field_schema

-- ── Sync audit log ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hrms_sync_log (
  sync_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_id     UUID         NOT NULL REFERENCES hrms_connector_config(connector_id),
  tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
  sync_mode        VARCHAR(20)  NOT NULL DEFAULT 'PULL',
                   -- 'PULL' | 'WEBHOOK' | 'MANUAL'
  started_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_at     TIMESTAMPTZ,
  status           VARCHAR(20)  NOT NULL DEFAULT 'RUNNING',
                   -- 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED'
  docs_pushed      INTEGER      NOT NULL DEFAULT 0,
  docs_failed      INTEGER      NOT NULL DEFAULT 0,
  error_message    TEXT,
  cursor_before    TEXT,        -- delta cursor value before this sync run
  cursor_after     TEXT,        -- delta cursor value after (written on success)
  temporal_run_id  TEXT         -- Temporal workflow run ID for correlation
);

CREATE INDEX IF NOT EXISTS idx_hrms_sync_connector ON hrms_sync_log(connector_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_hrms_sync_tenant    ON hrms_sync_log(tenant_id, started_at DESC);

-- ── Seed: two connector definitions (Darwinbox + Keka) ───────────────────────

INSERT INTO hrms_connector_definition
  (connector_key, display_name, auth_method, supported_modes, canonical_field_schema, docs_url)
VALUES
  (
    'darwinbox',
    'Darwinbox',
    'OAUTH2',
    ARRAY['PULL', 'WEBHOOK'],
    '{
      "employee_id":   "employee_id",
      "first_name":    "first_name",
      "last_name":     "last_name",
      "date_of_birth": "date_of_birth",
      "date_of_join":  "date_of_joining",
      "department":    "department",
      "designation":   "designation",
      "location":      "work_location",
      "manager_id":    "reporting_manager_id",
      "status":        "employment_status"
    }',
    'https://developers.darwinbox.com/'
  ),
  (
    'keka',
    'Keka HR',
    'API_KEY',
    ARRAY['PULL', 'WEBHOOK'],
    '{
      "employee_id":   "employeeNumber",
      "first_name":    "firstName",
      "last_name":     "lastName",
      "date_of_birth": "dateOfBirth",
      "date_of_join":  "joiningDate",
      "department":    "department.name",
      "designation":   "jobTitle",
      "location":      "workLocation.name",
      "manager_id":    "reportsTo.employeeNumber",
      "status":        "employmentStatus"
    }',
    'https://apidocs.keka.com/'
  )
ON CONFLICT (connector_key) DO NOTHING;
