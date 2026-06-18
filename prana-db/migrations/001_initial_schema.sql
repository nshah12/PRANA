-- Migration 001: Initial schema
-- Applies the full PRANA schema to a fresh YugabyteDB cluster.
-- Run once on first deploy. All subsequent changes go in 002_, 003_, etc.
-- Never edit this file after it has been applied to any environment.
--
-- ROLLBACK: DROP SCHEMA public CASCADE; CREATE SCHEMA public;

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Record this migration before DDL so a partial run is detectable
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(10)  PRIMARY KEY,
  description TEXT         NOT NULL,
  applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations(version, description) VALUES ('001', 'Initial schema — 26 tables across 11 layers');

-- ============================================================
-- LAYER 1
-- ============================================================

CREATE TABLE employee_user (
  employee_user_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token           VARCHAR(64)  NOT NULL UNIQUE,
  enc_pan             VARCHAR(20)  NOT NULL,
  enc_dek             TEXT         NOT NULL,
  mobile              VARCHAR(20)  UNIQUE,
  email               VARCHAR(254) UNIQUE,
  password_hash       TEXT,
  totp_secret_enc     TEXT,
  totp_configured_at  TIMESTAMPTZ,
  preferred_language  VARCHAR(5)   DEFAULT 'en',
  status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING_ACTIVATION',
  force_reset         BOOLEAN      DEFAULT FALSE,
  failed_totp_count   SMALLINT     DEFAULT 0,
  last_login_at       TIMESTAMPTZ,
  activated_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_eu_login_handle CHECK (
    mobile IS NOT NULL OR email IS NOT NULL OR status = 'PENDING_ACTIVATION'
  )
);
CREATE INDEX idx_eu_pan_token ON employee_user(pan_token);
CREATE INDEX idx_eu_mobile    ON employee_user(mobile) WHERE mobile IS NOT NULL;
CREATE INDEX idx_eu_email     ON employee_user(email)  WHERE email  IS NOT NULL;

-- ============================================================
-- LAYER 2
-- ============================================================

CREATE TABLE tenant (
  tenant_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_name         VARCHAR(200) NOT NULL,
  cin                 VARCHAR(21)  UNIQUE,
  gstin               VARCHAR(15)  UNIQUE,
  domain              VARCHAR(100) NOT NULL UNIQUE,
  nik_type            VARCHAR(20)  NOT NULL DEFAULT 'PAN',
  kek_arn             TEXT         NOT NULL,
  primary_state       VARCHAR(50)  NOT NULL,
  home_region         VARCHAR(20)  NOT NULL CHECK (home_region IN ('ap-south-1','ap-south-2')),
  geo_assigned_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  push_window_months  SMALLINT     DEFAULT 6 CHECK (push_window_months BETWEEN 3 AND 12),
  default_language    VARCHAR(5)   DEFAULT 'en',
  status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  storage_quota_gb    INTEGER      DEFAULT 50,
  office_ip_ranges    INET[],
  office_vpn_asns     INTEGER[],
  self_upload_policy  VARCHAR(30)  NOT NULL DEFAULT 'ALLOWED_WITH_WARNING'
                       CHECK (self_upload_policy IN (
                         'ALLOWED','ALLOWED_WITH_WARNING',
                         'BLOCKED_ON_OFFICE_NETWORK','BLOCKED_ENTIRELY')),
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tenant_region ON tenant(home_region, status);
CREATE INDEX idx_tenant_domain ON tenant(domain);

-- ============================================================
-- LAYER 3
-- ============================================================

CREATE TABLE employee_master (
  employee_uuid       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id    UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id           UUID         NOT NULL REFERENCES tenant(tenant_id),
  pan_token           VARCHAR(64)  NOT NULL,
  enc_pan             TEXT         NOT NULL,
  enc_dek             TEXT         NOT NULL,
  emp_id_org          VARCHAR(50),
  full_name           VARCHAR(200) NOT NULL,
  name_embedding      VECTOR(1536),
  designation         VARCHAR(150),
  department          VARCHAR(150),
  reporting_manager   VARCHAR(200),
  grade               VARCHAR(50),
  location            VARCHAR(100),
  employment_type     VARCHAR(30)  DEFAULT 'PERMANENT',
  cost_centre         VARCHAR(50),
  uan                 VARCHAR(12),
  doj                 DATE         NOT NULL,
  dol                 DATE,
  push_window_expires DATE,
  can_push            BOOLEAN      NOT NULL DEFAULT TRUE,
  status              VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
  vault_completeness  DECIMAL(5,2) DEFAULT 0,
  created_by          UUID,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_em_pan_per_tenant   UNIQUE (tenant_id, pan_token),
  CONSTRAINT uq_em_empid_per_tenant UNIQUE (tenant_id, emp_id_org),
  CONSTRAINT uq_em_tenure           UNIQUE (employee_user_id, tenant_id, doj),
  CONSTRAINT chk_em_dol_after_doj   CHECK (dol IS NULL OR dol > doj)
);
CREATE INDEX idx_em_user_id    ON employee_master(employee_user_id);
CREATE INDEX idx_em_tenant     ON employee_master(tenant_id);
CREATE INDEX idx_em_active     ON employee_master(tenant_id) WHERE dol IS NULL;
CREATE INDEX idx_emp_pan_token ON employee_master(pan_token);
CREATE INDEX idx_emp_name_trgm ON employee_master USING GIN (full_name gin_trgm_ops);
CREATE INDEX idx_emp_embedding ON employee_master USING ivfflat (name_embedding vector_cosine_ops);

CREATE TABLE employee_master_history (
  history_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_uuid   UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  field_name      VARCHAR(50)  NOT NULL,
  old_value       TEXT,
  new_value       TEXT         NOT NULL,
  change_reason   VARCHAR(100),
  changed_by      UUID         NOT NULL,
  changed_by_role VARCHAR(20)  NOT NULL,
  change_source   VARCHAR(20)  NOT NULL DEFAULT 'MANUAL',
  elevation_id    UUID,
  changed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_emh_employee ON employee_master_history(employee_uuid, changed_at DESC);
CREATE INDEX idx_emh_tenant   ON employee_master_history(tenant_id, changed_at DESC);

CREATE TABLE career_event (
  career_event_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token        VARCHAR(64)  NOT NULL,
  employee_user_id UUID         REFERENCES employee_user(employee_user_id),
  employee_uuid    UUID         REFERENCES employee_master(employee_uuid),
  tenant_id        UUID         REFERENCES tenant(tenant_id),
  event_type       VARCHAR(30)  NOT NULL,
  event_date       DATE         NOT NULL,
  event_title      VARCHAR(200),
  designation      VARCHAR(100),
  ctc_annual       BIGINT,
  grade            VARCHAR(20),
  verified         BOOLEAN      NOT NULL DEFAULT FALSE,
  doc_uuid         UUID,
  insight_text     TEXT,
  metadata         JSONB,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ce_pan_token ON career_event(pan_token, event_date DESC);
CREATE INDEX idx_ce_user      ON career_event(employee_user_id, event_date DESC);
CREATE INDEX idx_ce_tenant    ON career_event(tenant_id, event_date DESC);
CREATE INDEX idx_ce_meta      ON career_event USING GIN (metadata);

-- ============================================================
-- LAYER 4
-- ============================================================

CREATE TABLE oa_user (
  oa_user_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               UUID         NOT NULL REFERENCES tenant(tenant_id),
  email                   VARCHAR(254) NOT NULL UNIQUE,
  role                    VARCHAR(20)  NOT NULL CHECK (role IN ('oa_operator','oa_admin','chro','cfo','ciso')),
  password_hash           TEXT,
  temp_password_hash      TEXT,
  totp_secret_enc         TEXT,
  totp_configured_at      TIMESTAMPTZ,
  force_reset             BOOLEAN      DEFAULT TRUE,
  status                  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
  failed_totp_count       SMALLINT     DEFAULT 0,
  linked_employee_user_id UUID         REFERENCES employee_user(employee_user_id),
  created_by              UUID,
  last_login_at           TIMESTAMPTZ,
  created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_oa_tenant        ON oa_user(tenant_id, role);
CREATE INDEX idx_oa_active_admin  ON oa_user(tenant_id) WHERE role='oa_admin' AND status='ACTIVE';
CREATE INDEX idx_oa_linked_emp    ON oa_user(linked_employee_user_id) WHERE linked_employee_user_id IS NOT NULL AND status='ACTIVE';

CREATE TABLE chro_user (
  chro_id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 UUID         NOT NULL REFERENCES tenant(tenant_id),
  oa_user_id                UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  digest_weekly             BOOLEAN      DEFAULT TRUE,
  digest_monthly            BOOLEAN      DEFAULT TRUE,
  digest_quarterly          BOOLEAN      DEFAULT TRUE,
  alert_deadline_days       SMALLINT     DEFAULT 7 CHECK (alert_deadline_days IN (7,14,30)),
  alert_vault_threshold     SMALLINT     DEFAULT 80,
  alert_exception_threshold SMALLINT     DEFAULT 20,
  alert_exit_days           SMALLINT     DEFAULT 7,
  created_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_chro_oa  ON chro_user(oa_user_id);
CREATE INDEX idx_chro_tenant     ON chro_user(tenant_id);

CREATE TABLE portal_admin (
  pa_id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  email               VARCHAR(254) NOT NULL UNIQUE,
  password_hash       TEXT         NOT NULL,
  totp_secret_enc     TEXT,
  totp_configured_at  TIMESTAMPTZ,
  status              VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
  failed_totp_count   SMALLINT     DEFAULT 0,
  last_login_at       TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_pa_domain CHECK (email LIKE '%@prana.in')
);

-- ============================================================
-- LAYER 5
-- ============================================================

CREATE TABLE user_session (
  session_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type            VARCHAR(20)  NOT NULL,
  user_id              UUID         NOT NULL,
  refresh_token_hash   TEXT         NOT NULL UNIQUE,
  ip_address           INET,
  user_agent           TEXT,
  jwt_expires_at       TIMESTAMPTZ  NOT NULL,
  refresh_expires_at   TIMESTAMPTZ  NOT NULL,
  revoked              BOOLEAN      DEFAULT FALSE,
  revoked_reason       VARCHAR(40),
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_session_user    ON user_session(user_type, user_id) WHERE revoked=FALSE;
CREATE INDEX idx_session_refresh ON user_session(refresh_token_hash) WHERE revoked=FALSE;
CREATE INDEX idx_session_expiry  ON user_session(refresh_expires_at) WHERE revoked=FALSE;

CREATE TABLE backup_code (
  code_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type  VARCHAR(20)  NOT NULL,
  user_id    UUID         NOT NULL,
  code_hash  TEXT         NOT NULL UNIQUE,
  used       BOOLEAN      DEFAULT FALSE,
  used_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_backup_user ON backup_code(user_type, user_id) WHERE used=FALSE;

CREATE TABLE login_attempt_log (
  attempt_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type               VARCHAR(20)  NOT NULL,
  user_id                 UUID,
  identifier_hash         TEXT,
  tenant_id               UUID         REFERENCES tenant(tenant_id),
  attempt_type            VARCHAR(20)  NOT NULL,
  outcome                 VARCHAR(20)  NOT NULL,
  failure_reason          VARCHAR(50),
  session_id              UUID         REFERENCES user_session(session_id),
  ip_address              INET         NOT NULL,
  ip_country              VARCHAR(2),
  ip_city                 VARCHAR(100),
  user_agent              TEXT,
  device_type             VARCHAR(20),
  consecutive_failures    SMALLINT,
  is_flagged              BOOLEAN      DEFAULT FALSE,
  flag_reason             VARCHAR(50),
  device_fingerprint_hash TEXT,
  is_known_device         BOOLEAN,
  request_id              UUID,
  client_reported_tz      VARCHAR(40),
  client_reported_time    TIMESTAMPTZ,
  entry_point             VARCHAR(30),
  is_vpn_or_proxy         BOOLEAN,
  is_tor                  BOOLEAN,
  is_datacenter_ip        BOOLEAN,
  asn                     INTEGER,
  isp_name                VARCHAR(200),
  ip_risk_score           SMALLINT,
  geo_confidence_km       SMALLINT,
  geo_lat                 DECIMAL(9,6),
  geo_lon                 DECIMAL(9,6),
  enrichment_status       VARCHAR(20)  DEFAULT 'PENDING',
  enriched_at             TIMESTAMPTZ,
  attempted_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_lal_user        ON login_attempt_log(user_type, user_id, attempted_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX idx_lal_ip          ON login_attempt_log(ip_address, attempted_at DESC);
CREATE INDEX idx_lal_failed      ON login_attempt_log(user_type, user_id, attempted_at DESC) WHERE outcome='FAILED';
CREATE INDEX idx_lal_enrichment  ON login_attempt_log(attempted_at) WHERE enrichment_status='PENDING';
CREATE INDEX idx_lal_flagged     ON login_attempt_log(attempted_at DESC) WHERE is_flagged=TRUE;
CREATE INDEX idx_lal_fingerprint ON login_attempt_log(device_fingerprint_hash) WHERE device_fingerprint_hash IS NOT NULL;

CREATE TABLE trusted_device (
  trusted_device_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type               VARCHAR(20)  NOT NULL,
  user_id                 UUID         NOT NULL,
  device_fingerprint_hash TEXT         NOT NULL,
  label                   VARCHAR(100),
  first_seen_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_seen_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  trust_source            VARCHAR(30)  NOT NULL DEFAULT 'AUTO_FIRST_LOGIN',
  revoked                 BOOLEAN      DEFAULT FALSE,
  revoked_at              TIMESTAMPTZ,
  CONSTRAINT uq_trusted_device UNIQUE (user_type, user_id, device_fingerprint_hash)
);
CREATE INDEX idx_td_user ON trusted_device(user_type, user_id) WHERE revoked=FALSE;

CREATE TABLE device_credential (
  device_credential_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id        UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  public_key              TEXT         NOT NULL UNIQUE,
  device_fingerprint_hash TEXT,
  platform                VARCHAR(20)  NOT NULL,
  biometric_enrolled      BOOLEAN      DEFAULT FALSE,
  push_token              TEXT,
  registered_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_used_at            TIMESTAMPTZ,
  revoked                 BOOLEAN      DEFAULT FALSE
);
CREATE INDEX idx_dc_employee ON device_credential(employee_user_id) WHERE revoked=FALSE;

CREATE TABLE elevation_request (
  elevation_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  requestor_id    UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  approver_id     UUID         REFERENCES oa_user(oa_user_id),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  reason          TEXT         NOT NULL,
  duration_hours  SMALLINT     NOT NULL CHECK (duration_hours IN (2,4,8)),
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  expires_at      TIMESTAMPTZ,
  requested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  approved_at     TIMESTAMPTZ
);
CREATE INDEX idx_elev_tenant ON elevation_request(tenant_id, status);
CREATE INDEX idx_elev_expiry ON elevation_request(expires_at) WHERE status='ACTIVE';

ALTER TABLE employee_master_history
  ADD CONSTRAINT fk_emh_elevation
  FOREIGN KEY (elevation_id) REFERENCES elevation_request(elevation_id);

CREATE TABLE account_status_event (
  event_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type             VARCHAR(20)  NOT NULL,
  user_id               UUID         NOT NULL,
  tenant_id             UUID         REFERENCES tenant(tenant_id),
  event_type            VARCHAR(40)  NOT NULL,
  from_status           VARCHAR(20)  NOT NULL,
  to_status             VARCHAR(20)  NOT NULL,
  reason_code           VARCHAR(40)  NOT NULL,
  reason_note           TEXT,
  actor_type            VARCHAR(20)  NOT NULL,
  actor_id              UUID,
  actor_ip              INET,
  actor_session_id      UUID         REFERENCES user_session(session_id),
  elevation_id          UUID         REFERENCES elevation_request(elevation_id),
  failed_attempt_count  SMALLINT,
  last_failed_ip        INET,
  scheduled_unlock_at   TIMESTAMPTZ,
  reversed_by_event_id  UUID         REFERENCES account_status_event(event_id),
  notified_user         BOOLEAN      DEFAULT FALSE,
  notified_admin        BOOLEAN      DEFAULT FALSE,
  occurred_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ase_user       ON account_status_event(user_type, user_id, occurred_at DESC);
CREATE INDEX idx_ase_tenant     ON account_status_event(tenant_id, occurred_at DESC) WHERE tenant_id IS NOT NULL;
CREATE INDEX idx_ase_unresolved ON account_status_event(user_type, user_id)
  WHERE reversed_by_event_id IS NULL
  AND   event_type IN ('ADMIN_DISABLED','TOTP_LOCKOUT','PA_SUSPENDED','PASSWORD_LOCKOUT','POLICY_LOCK');
CREATE INDEX idx_ase_unlock     ON account_status_event(scheduled_unlock_at)
  WHERE event_type='POLICY_LOCK' AND reversed_by_event_id IS NULL;

CREATE TABLE api_key (
  api_key_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID         NOT NULL REFERENCES tenant(tenant_id),
  key_prefix          VARCHAR(20)  NOT NULL,
  key_hash            TEXT         NOT NULL UNIQUE,
  signing_secret_enc  TEXT         NOT NULL,
  label               VARCHAR(100),
  integration_type    VARCHAR(30),
  scopes              TEXT[]       NOT NULL,
  ip_allowlist        INET[],
  rate_limit_rpm      INTEGER      DEFAULT 1000,
  environment         VARCHAR(10)  DEFAULT 'live',
  status              VARCHAR(20)  DEFAULT 'ACTIVE',
  last_used_at        TIMESTAMPTZ,
  created_by          UUID,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_apikey_tenant ON api_key(tenant_id) WHERE status='ACTIVE';
CREATE INDEX idx_apikey_hash   ON api_key(key_hash);

-- ============================================================
-- LAYER 6
-- ============================================================

CREATE TABLE document (
  document_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID         REFERENCES tenant(tenant_id),
  employee_uuid         UUID         REFERENCES employee_master(employee_uuid),
  pan_token             VARCHAR(64),
  doc_type              VARCHAR(30)  NOT NULL,
  doc_period            VARCHAR(20),
  s3_key                TEXT         UNIQUE,
  s3_bucket             VARCHAR(100),
  file_size_bytes       INTEGER,
  file_hash_sha256      VARCHAR(64),
  virus_scan_status     VARCHAR(20)  DEFAULT 'PENDING',
  nsfw_scan_status      VARCHAR(20)  DEFAULT 'PENDING',
  csam_detected         BOOLEAN      NOT NULL DEFAULT FALSE,
  resolution_method     VARCHAR(30),
  resolution_confidence DECIMAL(4,3),
  extracted_fields      JSONB,
  pipeline_status       VARCHAR(20)  DEFAULT 'QUEUED',
  uploaded_by_oa        UUID         REFERENCES oa_user(oa_user_id),
  batch_id              UUID,
  is_self_upload        BOOLEAN      DEFAULT FALSE,
  is_deleted            BOOLEAN      DEFAULT FALSE,
  pushed_at             TIMESTAMPTZ  DEFAULT NOW(),
  routed_at             TIMESTAMPTZ
);
CREATE INDEX idx_doc_pan_token ON document(pan_token) WHERE is_deleted=FALSE;
CREATE INDEX idx_doc_pipeline  ON document(pipeline_status) WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION');
CREATE INDEX idx_doc_employee  ON document(employee_uuid, doc_type);
CREATE INDEX idx_doc_tenant    ON document(tenant_id, pipeline_status);
CREATE INDEX idx_doc_extracted ON document USING GIN (extracted_fields);

ALTER TABLE career_event
  ADD CONSTRAINT fk_ce_doc FOREIGN KEY (doc_uuid) REFERENCES document(document_id);

CREATE TABLE share_token (
  token_id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash           VARCHAR(64)  NOT NULL UNIQUE,
  pan_token            VARCHAR(64)  NOT NULL,
  employee_user_id     UUID         REFERENCES employee_user(employee_user_id),
  document_ids         UUID[]       NOT NULL,
  tenant_id            UUID         REFERENCES tenant(tenant_id),
  recipient_identifier TEXT         NOT NULL,
  access_type          VARCHAR(20)  NOT NULL,
  expires_at           TIMESTAMPTZ  NOT NULL,
  usage_limit          INTEGER,
  usage_count          INTEGER      NOT NULL DEFAULT 0,
  otp_required         BOOLEAN      DEFAULT FALSE,
  watermark_text       TEXT,
  status               VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
  revoked_at           TIMESTAMPTZ,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_share_hash   ON share_token(token_hash);
CREATE INDEX idx_share_active ON share_token(expires_at) WHERE status='ACTIVE';
CREATE INDEX idx_share_pan    ON share_token(pan_token)  WHERE status='ACTIVE';

CREATE TABLE document_access_log (
  access_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id       UUID         NOT NULL REFERENCES document(document_id),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  employee_uuid     UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id),
  actor_type        VARCHAR(30)  NOT NULL,
  actor_id          UUID,
  access_type       VARCHAR(20)  NOT NULL,
  access_channel    VARCHAR(20)  NOT NULL DEFAULT 'WEB',
  ip_address        INET         NOT NULL,
  ip_country        VARCHAR(2),
  ip_city           VARCHAR(100),
  user_agent        TEXT,
  device_type       VARCHAR(20),
  session_id        UUID         REFERENCES user_session(session_id),
  elevation_id      UUID         REFERENCES elevation_request(elevation_id),
  share_token_id    UUID         REFERENCES share_token(token_id),
  watermark_applied BOOLEAN      NOT NULL DEFAULT TRUE,
  watermark_ref     VARCHAR(100),
  file_size_bytes   INTEGER,
  is_flagged        BOOLEAN      DEFAULT FALSE,
  flag_reason       VARCHAR(100),
  accessed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dal_employee  ON document_access_log(employee_user_id, accessed_at DESC);
CREATE INDEX idx_dal_document  ON document_access_log(document_id, accessed_at DESC);
CREATE INDEX idx_dal_tenant    ON document_access_log(tenant_id, accessed_at DESC);
CREATE INDEX idx_dal_ip        ON document_access_log(ip_address, accessed_at DESC);
CREATE INDEX idx_dal_flagged   ON document_access_log(tenant_id, accessed_at DESC) WHERE is_flagged=TRUE;
CREATE INDEX idx_dal_watermark ON document_access_log(watermark_ref) WHERE watermark_ref IS NOT NULL;

-- ============================================================
-- LAYER 7
-- ============================================================

CREATE TABLE exception_queue (
  exception_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id            UUID         NOT NULL REFERENCES document(document_id),
  tenant_id              UUID         NOT NULL REFERENCES tenant(tenant_id),
  exception_type         VARCHAR(30)  NOT NULL,
  extracted_fields       JSONB,
  candidate_matches      JSONB,
  resolved_by            UUID         REFERENCES oa_user(oa_user_id),
  resolved_employee_uuid UUID         REFERENCES employee_master(employee_uuid),
  status                 VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
  raised_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  resolved_at            TIMESTAMPTZ
);
CREATE INDEX idx_exc_open ON exception_queue(tenant_id, raised_at) WHERE status='OPEN';
CREATE INDEX idx_exc_doc  ON exception_queue(document_id);

CREATE TABLE document_request (
  doc_request_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token        VARCHAR(64)  NOT NULL,
  tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
  doc_type         VARCHAR(30)  NOT NULL,
  period           VARCHAR(20),
  status           VARCHAR(20)  NOT NULL DEFAULT 'SENT',
  oaadm_uuid       UUID         REFERENCES oa_user(oa_user_id),
  note             TEXT,
  requested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at  TIMESTAMPTZ,
  fulfilled_at     TIMESTAMPTZ
);
CREATE INDEX idx_docreq_pan    ON document_request(pan_token, requested_at DESC);
CREATE INDEX idx_docreq_tenant ON document_request(tenant_id, status);

-- ============================================================
-- LAYER 8
-- ============================================================

CREATE TABLE dpdp_grievance (
  grievance_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token        VARCHAR(64)  NOT NULL,
  grievance_type   VARCHAR(30)  NOT NULL,
  description      TEXT         NOT NULL,
  status           VARCHAR(30)  NOT NULL DEFAULT 'RAISED',
  raised_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at  TIMESTAMPTZ,
  resolved_at      TIMESTAMPTZ,
  resolution_note  TEXT,
  dpb_escalated    BOOLEAN      NOT NULL DEFAULT FALSE,
  dpb_escalated_at TIMESTAMPTZ
);
CREATE INDEX idx_grievance_pan  ON dpdp_grievance(pan_token, raised_at DESC);
CREATE INDEX idx_grievance_open ON dpdp_grievance(raised_at)
  WHERE status NOT IN ('RESOLVED','ESCALATED_TO_DPB');

CREATE TABLE nominee (
  nominee_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token            VARCHAR(64)  NOT NULL UNIQUE,
  nominee_name         VARCHAR(100) NOT NULL,
  nominee_relation     VARCHAR(30),
  nominee_mobile       VARCHAR(15),
  nominee_email        VARCHAR(100),
  activation_condition VARCHAR(15)  NOT NULL,
  id_verified          BOOLEAN      NOT NULL DEFAULT FALSE,
  activated_at         TIMESTAMPTZ,
  access_expires_at    TIMESTAMPTZ,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- LAYER 9
-- ============================================================

CREATE TABLE audit_event (
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
) PARTITION BY RANGE (occurred_at);
CREATE INDEX idx_audit_type   ON audit_event(event_type, occurred_at DESC);
CREATE INDEX idx_audit_actor  ON audit_event(actor_type, actor_id, occurred_at DESC);
CREATE INDEX idx_audit_tenant ON audit_event(tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_pan    ON audit_event(pan_token, occurred_at DESC);
CREATE INDEX idx_audit_doc    ON audit_event(document_id, occurred_at DESC);

-- Seed partition covering dev period
CREATE TABLE audit_event_2025 PARTITION OF audit_event
  FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE audit_event_2026 PARTITION OF audit_event
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE anomaly_event (
  anomaly_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID         REFERENCES tenant(tenant_id),
  rule_name      VARCHAR(40)  NOT NULL,
  severity       VARCHAR(5)   NOT NULL,
  actor_id       UUID,
  event_metadata JSONB,
  status         VARCHAR(20)  DEFAULT 'OPEN',
  detected_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (detected_at);
CREATE INDEX idx_anomaly_open ON anomaly_event(tenant_id, detected_at DESC) WHERE status='OPEN';
CREATE TABLE anomaly_event_2025 PARTITION OF anomaly_event FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE anomaly_event_2026 PARTITION OF anomaly_event FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE kms_key_log (
  log_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID         REFERENCES tenant(tenant_id),
  key_type         VARCHAR(30)  NOT NULL,
  event_type       VARCHAR(20)  NOT NULL,
  status           VARCHAR(20)  NOT NULL,
  rotation_trigger VARCHAR(20),
  dek_rewrap_count INTEGER      DEFAULT 0,
  checked_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (checked_at);
CREATE INDEX idx_kms_tenant ON kms_key_log(tenant_id, checked_at DESC);
CREATE INDEX idx_kms_errors ON kms_key_log(status) WHERE status != 'HEALTHY';
CREATE TABLE kms_key_log_2025 PARTITION OF kms_key_log FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE kms_key_log_2026 PARTITION OF kms_key_log FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- ============================================================
-- LAYER 10
-- ============================================================

CREATE TABLE pa_platform_summary (
  region           VARCHAR(20)  NOT NULL,
  tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
  vault_health_pct DECIMAL(5,2),
  active_threats   INTEGER      DEFAULT 0,
  kek_age_days     SMALLINT,
  last_updated     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (region, tenant_id)
) PARTITION BY HASH (tenant_id);
CREATE TABLE pa_platform_summary_0 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE pa_platform_summary_1 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE pa_platform_summary_2 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE pa_platform_summary_3 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 3);

CREATE TABLE vault_health_score (
  pan_token              VARCHAR(64)  PRIMARY KEY,
  overall_score          SMALLINT     NOT NULL DEFAULT 0,
  employment_proof_score SMALLINT     NOT NULL DEFAULT 0,
  salary_slip_score      SMALLINT     NOT NULL DEFAULT 0,
  form16_score           SMALLINT     NOT NULL DEFAULT 0,
  gap_count              SMALLINT     NOT NULL DEFAULT 0,
  gap_detail             JSONB        NOT NULL DEFAULT '[]',
  computed_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE salary_band (
  band_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID         REFERENCES tenant(tenant_id),
  doc_type      VARCHAR(30)  NOT NULL DEFAULT 'SALARY_SLIP',
  period        VARCHAR(20),
  grade         VARCHAR(50),
  department    VARCHAR(100),
  p25           BIGINT,
  p50           BIGINT,
  p75           BIGINT,
  sample_count  INTEGER,
  computed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_band_tenant ON salary_band(tenant_id, period, grade);

-- ============================================================
-- LAYER 11
-- ============================================================

CREATE TABLE platform_config (
  config_key    VARCHAR(100) PRIMARY KEY,
  config_value  TEXT         NOT NULL,
  value_type    VARCHAR(30)  NOT NULL CHECK (value_type IN (
                  'INTEGER','DURATION_MINUTES','DURATION_HOURS',
                  'DURATION_DAYS','BOOLEAN','STRING','CRON_EXPRESSION')),
  description   TEXT,
  min_value     TEXT,
  max_value     TEXT,
  updated_by    UUID         REFERENCES portal_admin(pa_id),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value) VALUES
  ('platform_summary_interval_minutes', '5',          'DURATION_MINUTES', 'PA Meta Dashboard refresh cadence', '1', '60'),
  ('clamav_update_interval_minutes',    '120',         'DURATION_MINUTES', 'ClamAV signature update frequency', '30', '1440'),
  ('staging_cleanup_hours',             '48',          'DURATION_HOURS',   'Orphaned staging file alert threshold', '24', '168'),
  ('vault_health_recompute_hours',      '24',          'DURATION_HOURS',   'Max age before vault health recomputed', '1', '168'),
  ('exception_sla_p50_hours',           '4',           'DURATION_HOURS',   'Exception queue P50 SLA', '1', '24'),
  ('exception_sla_p95_hours',           '24',          'DURATION_HOURS',   'Exception queue P95 SLA', '4', '48'),
  ('totp_lockout_cooldown_minutes',     '30',          'DURATION_MINUTES', 'Auto-unlock after TOTP lockout (employee)', '5', '1440'),
  ('retention_years_default',           '7',           'DURATION_DAYS',    'DPDP audit log hot-tier retention', '7', '10'),
  ('share_otp_ttl_minutes',             '10',          'DURATION_MINUTES', 'OTP TTL on C-Share access', '5', '30'),
  ('domain_verification_poll_minutes',  '15',          'DURATION_MINUTES', 'DNS TXT polling interval', '5', '60'),
  ('domain_verification_max_hours',     '48',          'DURATION_HOURS',   'Max domain verification window', '24', '168'),
  ('consent_rebump_window_days',        '30',          'DURATION_DAYS',    'Re-consent window on version bump', '14', '60'),
  ('dpdp_erasure_confirmation_days',    '30',          'DURATION_DAYS',    'Erasure confirmation window', '7', '30'),
  ('nominee_access_window_days',        '90',          'DURATION_DAYS',    'Nominee vault access window', '30', '180'),
  ('ask_rate_limit_per_hour',           '20',          'INTEGER',          'Max Ask PRANA queries per employee/hr', '5', '100'),
  ('cfo_cohort_minimum',                '30',          'INTEGER',          'Min cohort size before salary band published', '10', '100'),
  ('session_max_concurrent',            '5',           'INTEGER',          'Max concurrent sessions per user', '1', '10'),
  ('pa_totp_lock_threshold',            '3',           'INTEGER',          'PA TOTP failures before lock', '3', '5'),
  ('oa_totp_lock_threshold',            '5',           'INTEGER',          'OA/Employee TOTP failures before lock', '3', '10'),
  ('password_protected_session_ttl',    '10',          'DURATION_MINUTES', 'In-memory session TTL for password-protected doc', '5', '30'),
  ('jwt_ttl_minutes',                   '60',          'DURATION_MINUTES', 'JWT access token TTL', '15', '240'),
  ('refresh_token_ttl_days',            '7',           'DURATION_DAYS',    'JWT refresh token TTL', '1', '30'),
  ('digest_weekly_cron',                '0 6 * * MON', 'CRON_EXPRESSION',  'Weekly CHRO digest (06:00 IST)', NULL, NULL),
  ('digest_monthly_cron',               '0 6 1 * *',   'CRON_EXPRESSION',  'Monthly CHRO digest (1st, 06:00 IST)', NULL, NULL),
  ('kms_health_check_cron',             '0 2 * * *',   'CRON_EXPRESSION',  'Daily KMS health check (02:00 IST)', NULL, NULL),
  ('storage_quota_check_cron',          '0 1 * * *',   'CRON_EXPRESSION',  'Daily storage quota check (01:00 IST)', NULL, NULL);

CREATE TABLE tenant_config (
  tenant_id     UUID         NOT NULL REFERENCES tenant(tenant_id),
  config_key    VARCHAR(100) NOT NULL REFERENCES platform_config(config_key),
  config_value  TEXT         NOT NULL,
  updated_by    UUID         REFERENCES oa_user(oa_user_id),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, config_key)
);

COMMIT;

-- ROLLBACK: DROP SCHEMA public CASCADE; CREATE SCHEMA public;
