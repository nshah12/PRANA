-- PRANA Platform — YugabyteDB Schema
-- Source of truth: PRANA_UserMgmt_DataArchitecture_v25.html + PRANA_Portal_v52.html (Spec tab)
-- 26 tables across 9 layers | Dual-region: ap-south-1 (Mumbai) + ap-south-2 (Hyderabad)
-- DDL order is topologically safe (no forward FK references except where ALTER TABLE is used below)

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for name_embedding VECTOR(1536)

-- ============================================================
-- LAYER 1: CORE IDENTITY (no external deps)
-- ============================================================

CREATE TABLE employee_user (
  employee_user_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token           VARCHAR(64)  NOT NULL UNIQUE,    -- HMAC-SHA256(NIK, platform_secret)
  enc_pan             VARCHAR(20)  NOT NULL,            -- FF3-1 FPE(NIK, emp_DEK)
  enc_dek             TEXT         NOT NULL,            -- KMS_Encrypt(emp_DEK, tenant_KEK)
  mobile              VARCHAR(20)  UNIQUE,              -- E.164. Primary login handle.
  email               VARCHAR(254) UNIQUE,              -- Optional secondary login handle.
  password_hash       TEXT,                             -- Argon2id (time=2, mem=65536, p=2)
  totp_secret_enc     TEXT,                             -- AES-256-GCM encrypted base32 seed
  totp_configured_at  TIMESTAMPTZ,                      -- NULL = vault inaccessible until TOTP set
  preferred_language  VARCHAR(5)   DEFAULT 'en',
  consent_status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                       -- PENDING | GRANTED | REVOKED
  status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING_ACTIVATION',
                       -- PENDING_ACTIVATION | ACTIVE | LOCKED | SUSPENDED
  force_reset         BOOLEAN      DEFAULT FALSE,
  failed_totp_count   SMALLINT     DEFAULT 0,           -- Lock at 5
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
-- LAYER 2: MULTI-TENANCY
-- ============================================================

CREATE TABLE tenant (
  tenant_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_name         VARCHAR(200) NOT NULL,
  cin                 VARCHAR(21)  UNIQUE,              -- Company Identification Number (India)
  gstin               VARCHAR(15)  UNIQUE,              -- GST Identification Number
  domain              VARCHAR(100) NOT NULL UNIQUE,     -- Verified corporate email domain
  nik_type            VARCHAR(20)  NOT NULL DEFAULT 'PAN',
                       -- PAN | SSN | EMIRATES_ID | NI_NUMBER | NRIC | TFN | PASSPORT
  kek_arn             TEXT         NOT NULL,            -- AWS KMS key ARN in home_region
  primary_state       VARCHAR(50)  NOT NULL,            -- Indian state → geo-affinity routing
  home_region         VARCHAR(20)  NOT NULL
                       CHECK (home_region IN ('ap-south-1', 'ap-south-2')),
  -- WARNING: home_region is IMMUTABLE after TenantProvisioningWorkflow completes.
  -- No migration may alter it post-insert. Data residency obligation (DPDP Act S.17).
  geo_assigned_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  push_window_months  SMALLINT     DEFAULT 6
                       CHECK (push_window_months BETWEEN 3 AND 12),
  default_language    VARCHAR(5)   DEFAULT 'en',
  status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                       -- PENDING | ACTIVE | SUSPENDED | OFFBOARDED
  storage_quota_gb    INTEGER      DEFAULT 50,
  office_ip_ranges    INET[],
  office_vpn_asns     INTEGER[],
  self_upload_policy  VARCHAR(30)  NOT NULL DEFAULT 'ALLOWED_WITH_WARNING'
                       CHECK (self_upload_policy IN (
                         'ALLOWED',
                         'ALLOWED_WITH_WARNING',
                         'BLOCKED_ON_OFFICE_NETWORK',
                         'BLOCKED_ENTIRELY'
                       )),
  -- BFSI constraint: employee_choice OTP channel CANNOT be enabled for BFSI tenants.
  -- Enforced in TenantProvisioningWorkflow + OA-Admin config update API.
  data_residency_verified BOOLEAN    DEFAULT FALSE,
  last_residency_check    TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tenant_region ON tenant(home_region, status);
CREATE INDEX idx_tenant_domain ON tenant(domain);

-- ============================================================
-- LAYER 3: EMPLOYEE RECORDS
-- ============================================================

CREATE TABLE employee_master (
  employee_uuid       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id    UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id           UUID         NOT NULL REFERENCES tenant(tenant_id),
  pan_token           VARCHAR(64)  NOT NULL,            -- HMAC-SHA256. Primary vault anchor.
  enc_pan             TEXT         NOT NULL,            -- FF3-1 FPE per employment record
  enc_dek             TEXT         NOT NULL,            -- KMS-wrapped DEK for this record
  emp_id_org          VARCHAR(50),                      -- Employer's own employee ID (e.g. NPCI0042)
  full_name           VARCHAR(200) NOT NULL,
  name_embedding      VECTOR(1536),                     -- bge-m3 embed of "full_name dept designation"
  designation         VARCHAR(150),
  department          VARCHAR(150),
  reporting_manager   VARCHAR(200),
  grade               VARCHAR(50),
  location            VARCHAR(100),
  employment_type     VARCHAR(30)  DEFAULT 'PERMANENT',
                       -- PERMANENT | CONTRACT | INTERN | CONSULTANT
  cost_centre         VARCHAR(50),
  uan                 VARCHAR(12),                      -- Universal Account Number (persistent across employers)
  doj                 DATE         NOT NULL,
  dol                 DATE,                             -- NULL = currently active
  push_window_expires DATE,                             -- = dol + tenant.push_window_months
  can_push            BOOLEAN      NOT NULL DEFAULT TRUE,
  status              VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                       -- ACTIVE | ALUMNI | DEACTIVATED
  vault_completeness  DECIMAL(5,2) DEFAULT 0,
  created_by          UUID,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_em_pan_per_tenant  UNIQUE (tenant_id, pan_token),
  CONSTRAINT uq_em_empid_per_tenant UNIQUE (tenant_id, emp_id_org),
  CONSTRAINT uq_em_tenure          UNIQUE (employee_user_id, tenant_id, doj),
  CONSTRAINT chk_em_dol_after_doj  CHECK (dol IS NULL OR dol > doj)
);
CREATE INDEX idx_em_user_id    ON employee_master(employee_user_id);
CREATE INDEX idx_em_tenant     ON employee_master(tenant_id);
CREATE INDEX idx_em_active     ON employee_master(tenant_id) WHERE dol IS NULL;
CREATE INDEX idx_emp_pan_token ON employee_master(pan_token);
-- Resolution Ladder 3 — trigram name search:
CREATE INDEX idx_emp_name_trgm ON employee_master USING GIN (full_name gin_trgm_ops);
-- Resolution Ladder 4 — cosine similarity embedding search:
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
                   -- MANUAL | HRMS_SYNC | BATCH_UPLOAD | CORRECTION_WORKFLOW
  elevation_id    UUID,        -- FK added below after elevation_request is created
  changed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_emh_employee ON employee_master_history(employee_uuid, changed_at DESC);
CREATE INDEX idx_emh_tenant   ON employee_master_history(tenant_id, changed_at DESC);

CREATE TABLE career_event (
  career_event_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token        VARCHAR(64)  NOT NULL,               -- HMAC vault anchor (cross-tenant)
  employee_user_id UUID         REFERENCES employee_user(employee_user_id),
  employee_uuid    UUID         REFERENCES employee_master(employee_uuid),
  tenant_id        UUID         REFERENCES tenant(tenant_id),
  event_type       VARCHAR(30)  NOT NULL,
                    -- JOINED | PROMOTED | INCREMENT | EXITED | SELF_UPLOADED
  event_date       DATE         NOT NULL,
  event_title      VARCHAR(200),
  designation      VARCHAR(100),
  ctc_annual       BIGINT,      -- AES-256-GCM encrypted, value in paise. NEVER returned raw.
  grade            VARCHAR(20),
  verified         BOOLEAN      NOT NULL DEFAULT FALSE, -- TRUE = employer-pushed document
  doc_uuid         UUID,        -- FK to document added below
  insight_text     TEXT,        -- Pre-generated LLM insight. Ask PRANA reads from here.
  metadata         JSONB,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ce_pan_token ON career_event(pan_token, event_date DESC);
CREATE INDEX idx_ce_user      ON career_event(employee_user_id, event_date DESC);
CREATE INDEX idx_ce_tenant    ON career_event(tenant_id, event_date DESC);
CREATE INDEX idx_ce_meta      ON career_event USING GIN (metadata);

-- ============================================================
-- LAYER 4: USER MANAGEMENT (org and platform staff)
-- ============================================================

CREATE TABLE oa_user (
  oa_user_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               UUID         NOT NULL REFERENCES tenant(tenant_id),
  email                   VARCHAR(254) NOT NULL UNIQUE, -- Must match tenant.domain
  role                    VARCHAR(20)  NOT NULL
                           CHECK (role IN ('oa_operator','oa_admin','chro','cfo','ciso')),
  password_hash           TEXT,                         -- Argon2id. NULL on first creation.
  temp_password_hash      TEXT,                         -- Cleared on first force_reset login
  totp_secret_enc         TEXT,                         -- AES-256-GCM. NULL until TOTP setup.
  totp_configured_at      TIMESTAMPTZ,                  -- NULL = portal access blocked
  force_reset             BOOLEAN      DEFAULT TRUE,
  status                  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                           -- ACTIVE | LOCKED | SUSPENDED | DEACTIVATED
  failed_totp_count       SMALLINT     DEFAULT 0,       -- Lock at 5
  linked_employee_user_id UUID         REFERENCES employee_user(employee_user_id),
  created_by              UUID,
  last_login_at           TIMESTAMPTZ,
  created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
-- Minimum 1 OA-Admin constraint: enforced at API layer before demotion/deactivation.
-- Query to check: SELECT COUNT(*) FROM oa_user WHERE tenant_id=$1 AND role='oa_admin' AND status='ACTIVE'
-- API returns 409 MIN_ADMIN_CONSTRAINT if count would drop to 0.
CREATE INDEX idx_oa_tenant       ON oa_user(tenant_id, role);
CREATE INDEX idx_oa_active_admin ON oa_user(tenant_id)
  WHERE role = 'oa_admin' AND status = 'ACTIVE';
CREATE INDEX idx_oa_linked_emp   ON oa_user(linked_employee_user_id)
  WHERE linked_employee_user_id IS NOT NULL AND status = 'ACTIVE';

CREATE TABLE chro_user (
  chro_id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 UUID         NOT NULL REFERENCES tenant(tenant_id),
  oa_user_id                UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  -- CHRO is both an oa_user (role='chro') and has extended digest prefs stored here
  digest_weekly             BOOLEAN      DEFAULT TRUE,
  digest_monthly            BOOLEAN      DEFAULT TRUE,
  digest_quarterly          BOOLEAN      DEFAULT TRUE,
  alert_deadline_days       SMALLINT     DEFAULT 7
                             CHECK (alert_deadline_days IN (7, 14, 30)),
  alert_vault_threshold     SMALLINT     DEFAULT 80,   -- % completion below which to alert
  alert_exception_threshold SMALLINT     DEFAULT 20,   -- Open exception count threshold
  alert_exit_days           SMALLINT     DEFAULT 7,    -- Days after exit without pushed docs
  created_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_chro_oa ON chro_user(oa_user_id);
CREATE INDEX idx_chro_tenant    ON chro_user(tenant_id);

CREATE TABLE portal_admin (
  pa_id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  email               VARCHAR(254) NOT NULL UNIQUE,
  password_hash       TEXT         NOT NULL,            -- Argon2id, minimum 16 char policy
  totp_secret_enc     TEXT,
  totp_configured_at  TIMESTAMPTZ,
  status              VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
  failed_totp_count   SMALLINT     DEFAULT 0,           -- Lock at 3 (stricter than OA's 5)
  last_login_at       TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_pa_domain CHECK (email LIKE '%@prana.in')
);

-- ============================================================
-- LAYER 5: SESSION & AUTH
-- ============================================================

CREATE TABLE user_session (
  session_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  -- session_id IS the JWT JTI claim — used for instant revocation via Redis blocklist
  user_type            VARCHAR(20)  NOT NULL,  -- employee | oa_user | portal_admin
  user_id              UUID         NOT NULL,
  refresh_token_hash   TEXT         NOT NULL UNIQUE,
  ip_address           INET,
  user_agent           TEXT,
  jwt_expires_at       TIMESTAMPTZ  NOT NULL,  -- NOW() + 1 hour
  refresh_expires_at   TIMESTAMPTZ  NOT NULL,  -- NOW() + 7 days
  revoked              BOOLEAN      DEFAULT FALSE,
  revoked_reason       VARCHAR(40),
                        -- LOGOUT | FORCE_LOGOUT | SECURITY_EVENT | IMPOSSIBLE_TRAVEL | SESSION_LIMIT
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
  -- Session limit: max 5 concurrent per user. On 6th login, oldest session revoked (reason: SESSION_LIMIT).
);
CREATE INDEX idx_session_user    ON user_session(user_type, user_id) WHERE revoked = FALSE;
CREATE INDEX idx_session_refresh ON user_session(refresh_token_hash)  WHERE revoked = FALSE;
CREATE INDEX idx_session_expiry  ON user_session(refresh_expires_at)  WHERE revoked = FALSE;

CREATE TABLE backup_code (
  code_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type  VARCHAR(20)  NOT NULL,
  user_id    UUID         NOT NULL,
  code_hash  TEXT         NOT NULL UNIQUE,  -- SHA-256. Plaintext shown once at TOTP setup, never stored.
  used       BOOLEAN      DEFAULT FALSE,
  used_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
  -- 8 codes per user. Single-use. Format: PREFIX-XXXX-XXXX (PREFIX = first 4 chars of user_id).
);
CREATE INDEX idx_backup_user ON backup_code(user_type, user_id) WHERE used = FALSE;

CREATE TABLE login_attempt_log (
  attempt_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type               VARCHAR(20)  NOT NULL,
  user_id                 UUID,                          -- NULL if identifier couldn't be resolved
  identifier_hash         TEXT,                          -- SHA-256(email|mobile). Stored only when user_id is NULL.
  tenant_id               UUID         REFERENCES tenant(tenant_id),
  attempt_type            VARCHAR(20)  NOT NULL,
                           -- PASSWORD | TOTP | OTP_SMS | BACKUP_CODE | REFRESH | PASSKEY
  outcome                 VARCHAR(20)  NOT NULL,
                           -- SUCCESS | FAILED | BLOCKED | RATE_LIMITED
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
  -- Phase 1 (synchronous, client-supplied — enriched before response):
  device_fingerprint_hash TEXT,
  is_known_device         BOOLEAN,
  request_id              UUID,
  client_reported_tz      VARCHAR(40),
  client_reported_time    TIMESTAMPTZ,
  entry_point             VARCHAR(30),  -- MOBILE_APP | WEB_PORTAL | ADMIN_PORTAL | API
  -- Phase 2 (async IP-intelligence enrichment — run after response sent to client):
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
                           -- PENDING | DONE | FAILED
  enriched_at             TIMESTAMPTZ,
  attempted_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_lal_user        ON login_attempt_log(user_type, user_id, attempted_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX idx_lal_ip          ON login_attempt_log(ip_address, attempted_at DESC);
CREATE INDEX idx_lal_failed      ON login_attempt_log(user_type, user_id, attempted_at DESC) WHERE outcome = 'FAILED';
CREATE INDEX idx_lal_enrichment  ON login_attempt_log(attempted_at) WHERE enrichment_status = 'PENDING';
CREATE INDEX idx_lal_flagged     ON login_attempt_log(attempted_at DESC) WHERE is_flagged = TRUE;
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
                           -- AUTO_FIRST_LOGIN | MANUAL_TRUST | PASSKEY
  revoked                 BOOLEAN      DEFAULT FALSE,
  revoked_at              TIMESTAMPTZ,
  CONSTRAINT uq_trusted_device UNIQUE (user_type, user_id, device_fingerprint_hash)
);
CREATE INDEX idx_td_user ON trusted_device(user_type, user_id) WHERE revoked = FALSE;

CREATE TABLE device_credential (
  device_credential_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id        UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  public_key              TEXT         NOT NULL UNIQUE,  -- WebAuthn / FIDO2 public key
  device_fingerprint_hash TEXT,
  platform                VARCHAR(20)  NOT NULL,          -- ANDROID | IOS | WEB
  biometric_enrolled      BOOLEAN      DEFAULT FALSE,
  push_token              TEXT,
  registered_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_used_at            TIMESTAMPTZ,
  revoked                 BOOLEAN      DEFAULT FALSE
);
CREATE INDEX idx_dc_employee ON device_credential(employee_user_id) WHERE revoked = FALSE;

CREATE TABLE elevation_request (
  elevation_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  requestor_id    UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  approver_id     UUID         REFERENCES oa_user(oa_user_id),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  reason          TEXT         NOT NULL,
  duration_hours  SMALLINT     NOT NULL CHECK (duration_hours IN (2, 4, 8)),
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                   -- PENDING | APPROVED | DENIED | ACTIVE | EXPIRED | ENDED_EARLY
  expires_at      TIMESTAMPTZ,
  requested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  approved_at     TIMESTAMPTZ
);
CREATE INDEX idx_elev_tenant ON elevation_request(tenant_id, status);
CREATE INDEX idx_elev_expiry ON elevation_request(expires_at) WHERE status = 'ACTIVE';

-- Deferred FK: employee_master_history → elevation_request
ALTER TABLE employee_master_history
  ADD CONSTRAINT fk_emh_elevation
  FOREIGN KEY (elevation_id) REFERENCES elevation_request(elevation_id);

CREATE TABLE account_status_event (
  event_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_type             VARCHAR(20)  NOT NULL,
  user_id               UUID         NOT NULL,
  tenant_id             UUID         REFERENCES tenant(tenant_id),
  event_type            VARCHAR(40)  NOT NULL,
                         -- ADMIN_DISABLED | TOTP_LOCKOUT | PA_SUSPENDED | PASSWORD_LOCKOUT | POLICY_LOCK
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
  scheduled_unlock_at   TIMESTAMPTZ, -- Set for POLICY_LOCK: when TOTPLockoutWorkflow auto-unlocks
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
  WHERE event_type = 'POLICY_LOCK' AND reversed_by_event_id IS NULL;

CREATE TABLE api_key (
  api_key_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID         NOT NULL REFERENCES tenant(tenant_id),
  key_prefix          VARCHAR(20)  NOT NULL,
  key_hash            TEXT         NOT NULL UNIQUE,  -- SHA-256 of full key value
  signing_secret_enc  TEXT         NOT NULL,         -- AES-256-GCM encrypted HMAC secret
  label               VARCHAR(100),
  integration_type    VARCHAR(30),                   -- HRMS | PAYROLL | CUSTOM
  scopes              TEXT[]       NOT NULL,
  ip_allowlist        INET[],
  rate_limit_rpm      INTEGER      DEFAULT 1000,
  environment         VARCHAR(10)  DEFAULT 'live',   -- live | test
  status              VARCHAR(20)  DEFAULT 'ACTIVE',
  last_used_at        TIMESTAMPTZ,
  created_by          UUID,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_apikey_tenant ON api_key(tenant_id) WHERE status = 'ACTIVE';
CREATE INDEX idx_apikey_hash   ON api_key(key_hash);

-- ============================================================
-- LAYER 6: DOCUMENTS & SHARING
-- ============================================================

CREATE TABLE document (
  document_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            UUID         REFERENCES tenant(tenant_id),   -- NULL for self-uploads pending resolution
  employee_uuid        UUID         REFERENCES employee_master(employee_uuid), -- NULL until identity resolved
  pan_token            VARCHAR(64),                                  -- Vault anchor, primary predicate
  doc_type             VARCHAR(30)  NOT NULL,
                        -- SALARY_SLIP | FORM_16 | OFFER_LETTER | APPOINTMENT_LETTER |
                        -- INCREMENT_LETTER | PROMOTION_LETTER | RELIEVING_LETTER |
                        -- EXPERIENCE_LETTER | JOINING_LETTER | PF_ACKNOWLEDGEMENT |
                        -- BANK_STATEMENT | IT_RETURN | INVESTMENT_PROOF | APPRAISAL_LETTER |
                        -- BONUS_LETTER | GRATUITY_LETTER | FORM_12B | FORM_26AS |
                        -- SELF_UPLOAD
  doc_period           VARCHAR(20),
                        -- '2024-03' monthly | 'FY:2023-24' annual | ISO date for event letters
  s3_key               TEXT         UNIQUE,
                        -- Pattern: {tenant_id}/{employee_uuid}/{doc_type}/{period}_{uuid}.pdf
  s3_bucket            VARCHAR(100),
  file_size_bytes      INTEGER,
  file_hash_sha256     VARCHAR(64),                                  -- SHA-256 for integrity + dedup
  virus_scan_status    VARCHAR(20)  DEFAULT 'PENDING',
                        -- PENDING | CLEAN | QUARANTINED | FAILED
  nsfw_scan_status     VARCHAR(20)  DEFAULT 'PENDING',
                        -- PENDING | CLEAN | FLAGGED | REJECTED
  csam_detected        BOOLEAN      NOT NULL DEFAULT FALSE,
  -- CSAM retention: infinite, via wait_condition(lambda: False) in CsamReportWorkflow.
  -- CANNOT be deleted by ANY role including Portal Admin. POCSO Act 2012 obligation.
  resolution_method    VARCHAR(30),
                        -- PAN_TOKEN_EXACT | EMP_ID_EXACT | NAME_DOJ_FUZZY | EMBEDDING_SIMILARITY | MANUAL_OA
  resolution_confidence DECIMAL(4,3),
  extracted_fields     JSONB,
  -- extracted_fields schema: {field_name: {value: ..., confidence: 0.0-1.0}}
  -- NEVER contains raw ₹ salary, PAN numbers, or plaintext NIK.
  -- benchmark_service is the ONLY consumer of salary fields from extracted_fields.
  pipeline_status      VARCHAR(20)  DEFAULT 'QUEUED',
                        -- QUEUED | ENCRYPTING | SCANNING | EXTRACTING | RESOLVING | ROUTED | EXCEPTION
  uploaded_by_oa       UUID         REFERENCES oa_user(oa_user_id),
  batch_id             UUID,
  is_self_upload       BOOLEAN      DEFAULT FALSE,
  is_deleted           BOOLEAN      DEFAULT FALSE,   -- Soft delete. Blocked if active share_token exists.
  pushed_at            TIMESTAMPTZ  DEFAULT NOW(),
  routed_at            TIMESTAMPTZ,
  upload_comment       TEXT,        -- OA-Operator annotation at upload time
  original_filename    TEXT         -- Original filename from upload (not stored on S3)
);
CREATE INDEX idx_doc_pan_token ON document(pan_token) WHERE is_deleted = FALSE;
CREATE INDEX idx_doc_pipeline  ON document(pipeline_status) WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION');
CREATE INDEX idx_doc_employee  ON document(employee_uuid, doc_type);
CREATE INDEX idx_doc_tenant    ON document(tenant_id, pipeline_status);
CREATE INDEX idx_doc_extracted ON document USING GIN (extracted_fields);

-- Deferred FK: career_event → document
ALTER TABLE career_event
  ADD CONSTRAINT fk_ce_doc
  FOREIGN KEY (doc_uuid) REFERENCES document(document_id);

CREATE TABLE share_token (
  token_id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash           VARCHAR(64)  NOT NULL UNIQUE,  -- SHA-256 of URL-embedded token
  pan_token            VARCHAR(64)  NOT NULL,          -- Vault owner
  employee_user_id     UUID         REFERENCES employee_user(employee_user_id),
  document_ids         UUID[]       NOT NULL,
  tenant_id            UUID         REFERENCES tenant(tenant_id),
  recipient_identifier TEXT         NOT NULL,          -- Email or mobile (E.164) of recipient
  access_type          VARCHAR(20)  NOT NULL,
                        -- VIEW_ONLY | VIEW_DOWNLOAD | VERIFIED_API
  expires_at           TIMESTAMPTZ  NOT NULL,
  usage_limit          INTEGER,                        -- NULL = unlimited within expiry window
  usage_count          INTEGER      NOT NULL DEFAULT 0,
  otp_required         BOOLEAN      DEFAULT FALSE,
  watermark_text       TEXT,                           -- "recipient + timestamp + token_ref" applied on serve
  status               VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                        -- ACTIVE | EXPIRED | REVOKED
  revoked_at           TIMESTAMPTZ,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_share_hash   ON share_token(token_hash);
CREATE INDEX idx_share_active ON share_token(expires_at) WHERE status = 'ACTIVE';
CREATE INDEX idx_share_pan    ON share_token(pan_token)  WHERE status = 'ACTIVE';

CREATE TABLE document_access_log (
  access_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id       UUID         NOT NULL REFERENCES document(document_id),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  employee_uuid     UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id),
  actor_type        VARCHAR(30)  NOT NULL,
                     -- EMPLOYEE | OA_OPERATOR | OA_OPERATOR_ELEVATED | OA_ADMIN | THIRD_PARTY | NOMINEE
  actor_id          UUID,
  access_type       VARCHAR(20)  NOT NULL,  -- VIEW | DOWNLOAD | API_PULL | SHARE_VIEW
  access_channel    VARCHAR(20)  NOT NULL DEFAULT 'WEB',
                     -- WEB | MOBILE | API | SHARE_LINK
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
  -- Response shapes: CISO sees full ip_address; employee sees ip_city only.
  accessed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dal_employee  ON document_access_log(employee_user_id, accessed_at DESC);
CREATE INDEX idx_dal_document  ON document_access_log(document_id, accessed_at DESC);
CREATE INDEX idx_dal_tenant    ON document_access_log(tenant_id, accessed_at DESC);
CREATE INDEX idx_dal_ip        ON document_access_log(ip_address, accessed_at DESC);
CREATE INDEX idx_dal_flagged   ON document_access_log(tenant_id, accessed_at DESC) WHERE is_flagged = TRUE;
CREATE INDEX idx_dal_watermark ON document_access_log(watermark_ref) WHERE watermark_ref IS NOT NULL;

-- ============================================================
-- LAYER 7: EXCEPTIONS & REQUESTS
-- ============================================================

CREATE TABLE exception_queue (
  exception_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id            UUID         NOT NULL REFERENCES document(document_id),
  tenant_id              UUID         NOT NULL REFERENCES tenant(tenant_id),
  exception_type         VARCHAR(30)  NOT NULL,
                          -- NO_MATCH | MULTIPLE_CANDIDATES | LOW_CONFIDENCE
  extracted_fields       JSONB,                          -- Context shown to OA-Admin for manual resolution
  candidate_matches      JSONB,                          -- Top-3 candidates with confidence scores
  resolved_by            UUID         REFERENCES oa_user(oa_user_id),
  resolved_employee_uuid UUID         REFERENCES employee_master(employee_uuid),
  status                 VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
                          -- OPEN | RESOLVED | DISMISSED
  raised_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),  -- SLA clock starts here
  resolved_at            TIMESTAMPTZ
  -- SLA: P50 < 4hr, P95 < 24hr. PA escalated at 20hr (driven by exception_sla_p95_hours config).
);
CREATE INDEX idx_exc_open   ON exception_queue(tenant_id, raised_at) WHERE status = 'OPEN';
CREATE INDEX idx_exc_doc    ON exception_queue(document_id);

CREATE TABLE unclassified_queue (
  document_id          UUID         PRIMARY KEY REFERENCES document(document_id),
  tenant_id            UUID         NOT NULL REFERENCES tenant(tenant_id),
  reason               TEXT         NOT NULL,
    -- AUTO_DETECT_FAILED | LOW_CONFIDENCE | CONFLICTING_SIGNALS | OCR_POOR_QUALITY
  declared_doc_type    VARCHAR(50),
  best_guess_doc_type  VARCHAR(50),
  best_guess_score     NUMERIC(5,4),
  partial_fields       JSONB        NOT NULL DEFAULT '{}',
  status               VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    -- PENDING | RESOLVED | EXPIRED
  resolved_by          UUID         REFERENCES oa_user(oa_user_id),
  resolved_doc_type    VARCHAR(50),
  resolved_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_unclassified_tenant  ON unclassified_queue(tenant_id, status, created_at DESC);
CREATE INDEX idx_unclassified_pending ON unclassified_queue(tenant_id, created_at DESC)
  WHERE status = 'PENDING';

CREATE TABLE document_request (
  doc_request_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token        VARCHAR(64)  NOT NULL,               -- Employee who made the request
  tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
  doc_type         VARCHAR(30)  NOT NULL,
  period           VARCHAR(20),
  status           VARCHAR(20)  NOT NULL DEFAULT 'SENT',
                    -- SENT | ACKNOWLEDGED | IN_PROGRESS | FULFILLED | REJECTED | CANCELLED
  oaadm_uuid      UUID         REFERENCES oa_user(oa_user_id),
  note             TEXT,
  requested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at  TIMESTAMPTZ,
  fulfilled_at     TIMESTAMPTZ
);
CREATE INDEX idx_docreq_pan    ON document_request(pan_token, requested_at DESC);
CREATE INDEX idx_docreq_tenant ON document_request(tenant_id, status);

-- ============================================================
-- LAYER 8: COMPLIANCE & DPDP ACT 2023
-- ============================================================

CREATE TABLE employee_consent (
  consent_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  purpose           VARCHAR(50)  NOT NULL,
                    -- document_processing | insight_generation | peer_benchmark | notifications
  consent_version   VARCHAR(20)  NOT NULL DEFAULT '1.0',
  is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
  consented_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_consent_employee_purpose UNIQUE (employee_user_id, purpose)
);
CREATE INDEX idx_consent_employee ON employee_consent(employee_user_id, purpose);
CREATE INDEX idx_consent_inactive ON employee_consent(employee_user_id) WHERE is_active = FALSE;

CREATE TABLE erasure_request (
  erasure_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  reason            TEXT,
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | CANCELLED | EXECUTING | COMPLETE
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  confirmed_at      TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_erasure_employee ON erasure_request(employee_user_id, status);

CREATE TABLE data_export_request (
  export_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | IN_PROGRESS | READY | EXPIRED
  s3_key            TEXT,
  expires_at        TIMESTAMPTZ,
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_at      TIMESTAMPTZ
);
CREATE INDEX idx_export_employee ON data_export_request(employee_user_id, requested_at DESC);

CREATE TABLE data_correction_request (
  correction_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  field_name        VARCHAR(100) NOT NULL,
  current_value     TEXT,
  correct_value     TEXT         NOT NULL,
  evidence_note     TEXT,
  status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | UNDER_REVIEW | APPLIED | REJECTED
  reviewer_id       UUID         REFERENCES oa_user(oa_user_id),
  rejection_reason  TEXT,
  requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  resolved_at       TIMESTAMPTZ
);
CREATE INDEX idx_correction_employee ON data_correction_request(employee_user_id, status);
CREATE INDEX idx_correction_tenant   ON data_correction_request(tenant_id, status) WHERE status = 'PENDING';

CREATE TABLE dpdp_grievance (
  grievance_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         REFERENCES employee_user(employee_user_id),
  tenant_id         UUID         REFERENCES tenant(tenant_id),
  pan_token         VARCHAR(64),              -- HMAC of PAN — for audit analytics, may be NULL if pan not yet resolved
  grievance_type    VARCHAR(30)  NOT NULL,
                    -- ACCESS_DENIED | CORRECTION_REFUSED | ERASURE_REFUSED | DATA_BREACH | OTHER
  category          VARCHAR(50),
                    -- DATA_ACCURACY | ACCESS_DENIED | CORRECTION_REFUSED |
                    -- ERASURE_REFUSED | DATA_BREACH | NOTIFICATION | OTHER
  description       TEXT         NOT NULL,
  status            VARCHAR(30)  NOT NULL DEFAULT 'RAISED',
                    -- RAISED | ACKNOWLEDGED | IN_REVIEW | RESOLVED | ESCALATED_TO_DPB
  raised_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at   TIMESTAMPTZ,  -- STATUTORY: must be set within 7 working days (DPDP Act S.13)
  resolved_at       TIMESTAMPTZ,
  resolution_note   TEXT,
  dpb_escalated     BOOLEAN      NOT NULL DEFAULT FALSE,
  -- dpb_escalated = TRUE is IMMUTABLE once set. DPDPGrievanceWorkflow auto-escalates on day 8.
  dpb_escalated_at  TIMESTAMPTZ
);
CREATE INDEX idx_grievance_pan      ON dpdp_grievance(pan_token, raised_at DESC);
CREATE INDEX idx_grievance_employee ON dpdp_grievance(employee_user_id, raised_at DESC);
CREATE INDEX idx_grievance_tenant   ON dpdp_grievance(tenant_id, status);
CREATE INDEX idx_grievance_open     ON dpdp_grievance(raised_at)
  WHERE status NOT IN ('RESOLVED', 'ESCALATED_TO_DPB');

CREATE TABLE nominee (
  nominee_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  pan_token            VARCHAR(64)  NOT NULL UNIQUE,    -- One nominee per employee
  nominee_name         VARCHAR(100) NOT NULL,
  nominee_relation     VARCHAR(30),
  nominee_mobile       VARCHAR(15),
  nominee_email        VARCHAR(100),
  activation_condition VARCHAR(15)  NOT NULL,
                        -- DEATH | INCAPACITY | BOTH
  id_verified          BOOLEAN      NOT NULL DEFAULT FALSE,  -- Aadhaar OTP + death/medical cert
  activated_at         TIMESTAMPTZ,
  access_expires_at    TIMESTAMPTZ,  -- activated_at + nominee_access_window_days (config). Renewable.
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
  -- All nominee vault actions logged with actor_type = 'NOMINEE' in document_access_log.
);

-- ============================================================
-- LAYER 9: AUDIT, ANOMALY & SECURITY (partitioned)
-- ============================================================

CREATE TABLE audit_event (
  event_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type     VARCHAR(40)  NOT NULL,
                  -- DOC_PUSHED | DOC_ROUTED | DOC_OPENED | DOC_DOWNLOADED | DOC_DELETED |
                  -- SHARE_CREATED | SHARE_ACCESSED | SHARE_REVOKED | EXCEPTION_RAISED |
                  -- EXCEPTION_RESOLVED | LOGIN_SUCCESS | LOGIN_FAILED | TOTP_SETUP |
                  -- TOTP_FAILED | BACKUP_CODE_USED | PASSWORD_RESET | SESSION_REVOKED |
                  -- ACCOUNT_LOCKED | USER_CREATED | USER_DEACTIVATED | ROLE_CHANGED |
                  -- KEY_ROTATED | ELEVATION_ENDED_EARLY | SCAN_QUARANTINED | SCAN_CSAM |
                  -- BATCH_UPLOADED | EXTRACTION_COMPLETE | EXTRACTION_FAILED |
                  -- RESOLUTION_SUCCESS | CSAM_REPORT_SUBMITTED | TENANT_PROVISIONED
  actor_type     VARCHAR(30)  NOT NULL,
                  -- EMPLOYEE | OA_OPERATOR | OA_OPERATOR_ELEVATED | OA_ADMIN | PA | SYSTEM | NOMINEE
  actor_id       UUID         NOT NULL,
  tenant_id      UUID         REFERENCES tenant(tenant_id),
  pan_token      VARCHAR(64),                           -- NEVER plaintext NIK
  document_id    UUID,
  event_metadata JSONB,
  ip_address     INET,
  occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (occurred_at);
-- Monthly partitions: audit_event_2025_01, audit_event_2025_02, ...
-- Hot in YugabyteDB. Cold to Apache Iceberg on S3 via RetentionWorkflow after 30 days.
-- Retained hot for 7 years minimum (DPDP Act S.9). Never deleted from cold storage.
-- IMPORTANT: REVOKE UPDATE, DELETE ON audit_event FROM app_role — append-only by policy.
CREATE INDEX idx_audit_type   ON audit_event(event_type, occurred_at DESC);
CREATE INDEX idx_audit_actor  ON audit_event(actor_type, actor_id, occurred_at DESC);
CREATE INDEX idx_audit_tenant ON audit_event(tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_pan    ON audit_event(pan_token, occurred_at DESC);
CREATE INDEX idx_audit_doc    ON audit_event(document_id, occurred_at DESC);

CREATE TABLE anomaly_event (
  anomaly_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID         REFERENCES tenant(tenant_id),
  rule_name      VARCHAR(40)  NOT NULL,
                  -- IMPOSSIBLE_TRAVEL | BULK_DOC_ACCESS | SHARE_ENUM | OFF_HOURS_ACCESS |
                  -- BRUTE_FORCE | CROSS_TENANT_QUERY | PRE_EXIT_BULK | PRIVILEGE_ESCALATION
  severity       VARCHAR(5)   NOT NULL,                -- P0 | P1 | P2 | P3
  actor_id       UUID,
  event_metadata JSONB,                                -- {triggered_by_event_id, ips, counts, ...}
  status            VARCHAR(20)  DEFAULT 'OPEN',
                    -- OPEN | INVESTIGATING | RESOLVED | FALSE_POSITIVE
  acknowledged_by   UUID,
  acknowledged_at   TIMESTAMPTZ,
  financial_pattern TEXT,
  detected_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (detected_at);
-- Severity: P0 = immediate PA page; P1 = 1hr war room; P2 = next-business-day; P3 = weekly digest
-- P0 breach triggers BreachNotificationWorkflow: 72-hour DPB notification (DPDP Act S.35 STATUTORY)
CREATE INDEX idx_anomaly_open ON anomaly_event(tenant_id, detected_at DESC) WHERE status = 'OPEN';

CREATE TABLE kms_key_log (
  log_id           UUID         NOT NULL DEFAULT gen_random_uuid(),
  tenant_id        UUID         REFERENCES tenant(tenant_id),
  key_type         VARCHAR(30)  NOT NULL,  -- TENANT_KEK | PLATFORM_HMAC | JWT_SIGNING
  event_type       VARCHAR(20)  NOT NULL,  -- HEALTH_CHECK | ROTATED | ROTATION_FAILED
  status           VARCHAR(20)  NOT NULL,  -- HEALTHY | DEGRADED | ERROR | ROTATED
  rotation_trigger VARCHAR(20),            -- SCHEDULED | EMERGENCY | MANUAL_PA
  dek_rewrap_count INTEGER      DEFAULT 0, -- enc_dek rows re-wrapped during KEK rotation
  checked_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  -- HMACSecretRotationWorkflow requires 2 DISTINCT PA accounts (4-eyes enforcement).
  -- Estimated: 4-8 hours for 1 crore employees (DEK rewrap is the bottleneck).
  PRIMARY KEY (log_id, checked_at)
) PARTITION BY RANGE (checked_at);
CREATE INDEX idx_kms_tenant  ON kms_key_log(tenant_id, checked_at DESC);
CREATE INDEX idx_kms_errors  ON kms_key_log(status) WHERE status != 'HEALTHY';

-- ============================================================
-- LAYER 9b: HRMS CONNECTOR CONFIG (migration 013)
-- ============================================================

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

CREATE INDEX idx_hrms_conn_tenant ON hrms_connector_config(tenant_id) WHERE status = 'ACTIVE';
CREATE INDEX idx_hrms_conn_type   ON hrms_connector_config(tenant_id, connector_type);

-- ============================================================
-- LAYER 10: ANALYTICS & PLATFORM OPS
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
-- Refreshed every 5 min by PlatformSummaryWorkflow.
-- PA Meta Dashboard reads ONLY from this table — never from raw employee rows.

CREATE TABLE vault_health_score (
  pan_token              VARCHAR(64)  PRIMARY KEY,    -- One row per employee, upserted nightly
  overall_score          SMALLINT     NOT NULL DEFAULT 0,  -- 0–100
  employment_proof_score SMALLINT     NOT NULL DEFAULT 0,
  salary_slip_score      SMALLINT     NOT NULL DEFAULT 0,
  form16_score           SMALLINT     NOT NULL DEFAULT 0,
  gap_count              SMALLINT     NOT NULL DEFAULT 0,
  gap_detail             JSONB        NOT NULL DEFAULT '[]',
  -- [{doc_type, period, employer_name, action_available: "REQUEST"|"SELF_UPLOAD"}]
  computed_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE salary_band (
  band_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID         REFERENCES tenant(tenant_id),  -- NULL = platform-wide default
  doc_type      VARCHAR(30)  NOT NULL DEFAULT 'SALARY_SLIP',
  period        VARCHAR(20),
  grade         VARCHAR(50),
  department    VARCHAR(100),
  p25           BIGINT,   -- 25th percentile CTC in paise — encrypted at rest
  p50           BIGINT,   -- 50th percentile
  p75           BIGINT,   -- 75th percentile
  sample_count  INTEGER,  -- Must be >= 30 before band is published (CFO cohort minimum)
  computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
  -- benchmark_service is the ONLY consumer. Returns percentile labels, NEVER raw values.
  -- CFO queries returning cohort < 30 employees → {suppressed: true}
);
CREATE INDEX idx_band_tenant ON salary_band(tenant_id, period, grade);

-- ============================================================
-- LAYER 11: PLATFORM CONFIG (must be created last)
-- ============================================================

CREATE TABLE platform_config (
  config_key    VARCHAR(100) PRIMARY KEY,
  config_value  TEXT         NOT NULL,
  value_type    VARCHAR(30)  NOT NULL CHECK (value_type IN (
                  'INTEGER', 'DURATION_MINUTES', 'DURATION_HOURS',
                  'DURATION_DAYS', 'BOOLEAN', 'STRING', 'CRON_EXPRESSION'
                )),
  description   TEXT,
  min_value     TEXT,
  max_value     TEXT,
  updated_by    UUID         REFERENCES portal_admin(pa_id),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Config resolution pattern (always use this, never hardcode durations in code):
-- SELECT COALESCE(
--   (SELECT config_value FROM tenant_config  WHERE tenant_id = $1 AND config_key = $2),
--   (SELECT config_value FROM platform_config WHERE config_key = $2)
-- ) AS resolved_value;
-- Changes apply to NEW workflow instances only — running workflows use the value at start time.

INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value) VALUES
  ('platform_summary_interval_minutes', '5',          'DURATION_MINUTES', 'PA Meta Dashboard refresh cadence', '1', '60'),
  ('clamav_update_interval_minutes',    '120',         'DURATION_MINUTES', 'ClamAV signature DB update frequency', '30', '1440'),
  ('staging_cleanup_hours',             '48',          'DURATION_HOURS',   'Orphaned staging file alert threshold', '24', '168'),
  ('vault_health_recompute_hours',      '24',          'DURATION_HOURS',   'Max age before vault health score recomputed', '1', '168'),
  ('exception_sla_p50_hours',           '4',           'DURATION_HOURS',   'Exception queue P50 SLA', '1', '24'),
  ('exception_sla_p95_hours',           '24',          'DURATION_HOURS',   'Exception queue P95 SLA, PA escalation threshold', '4', '48'),
  ('totp_lockout_cooldown_minutes',     '30',          'DURATION_MINUTES', 'Auto-unlock cooldown after TOTP lockout (employee)', '5', '1440'),
  ('retention_years_default',           '7',           'DURATION_DAYS',    'DPDP audit log hot-tier retention (7-year minimum)', '7', '10'),
  ('share_otp_ttl_minutes',             '10',          'DURATION_MINUTES', 'OTP challenge TTL on C-Share access', '5', '30'),
  ('domain_verification_poll_minutes',  '15',          'DURATION_MINUTES', 'DNS TXT polling interval (DomainVerificationWorkflow)', '5', '60'),
  ('domain_verification_max_hours',     '48',          'DURATION_HOURS',   'Max domain verification window', '24', '168'),
  ('consent_rebump_window_days',        '30',          'DURATION_DAYS',    'Re-consent window on consent_version increment', '14', '60'),
  ('dpdp_erasure_confirmation_days',    '30',          'DURATION_DAYS',    'Erasure confirmation window', '7', '30'),
  ('nominee_access_window_days',        '90',          'DURATION_DAYS',    'Nominee vault access window post-activation', '30', '180'),
  ('ask_rate_limit_per_hour',           '20',          'INTEGER',          'Max Ask PRANA queries per employee per hour', '5', '100'),
  ('cfo_cohort_minimum',                '30',          'INTEGER',          'Min employees in cohort before salary band published', '10', '100'),
  ('digest_weekly_cron',                '0 6 * * MON', 'CRON_EXPRESSION',  'Weekly CHRO digest send time (IST = UTC+5:30)', NULL, NULL),
  ('digest_monthly_cron',               '0 6 1 * *',   'CRON_EXPRESSION',  'Monthly CHRO digest (1st of month, 06:00 IST)', NULL, NULL),
  ('kms_health_check_cron',             '0 2 * * *',   'CRON_EXPRESSION',  'Daily KMS health check (02:00 IST)', NULL, NULL),
  ('storage_quota_check_cron',          '0 1 * * *',   'CRON_EXPRESSION',  'Daily storage quota check (01:00 IST)', NULL, NULL),
  ('session_max_concurrent',            '5',           'INTEGER',          'Max concurrent sessions per user (6th login revokes oldest)', '1', '10'),
  ('pa_totp_lock_threshold',            '3',           'INTEGER',          'PA failed TOTP count before lock (stricter than OA 5)', '3', '5'),
  ('oa_totp_lock_threshold',            '5',           'INTEGER',          'OA/Employee failed TOTP count before lock', '3', '10'),
  ('password_protected_session_ttl',    '10',          'DURATION_MINUTES', 'In-memory session for password-protected doc (wiped on expiry)', '5', '30'),
  ('jwt_ttl_minutes',                   '60',          'DURATION_MINUTES', 'JWT access token TTL', '15', '240'),
  ('refresh_token_ttl_days',            '7',           'DURATION_DAYS',    'JWT refresh token TTL', '1', '30');

CREATE TABLE tenant_config (
  tenant_id     UUID         NOT NULL REFERENCES tenant(tenant_id),
  config_key    VARCHAR(100) NOT NULL REFERENCES platform_config(config_key),
  config_value  TEXT         NOT NULL,
  updated_by    UUID         REFERENCES oa_user(oa_user_id),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, config_key)
);

-- Layer 12: CFO / CHRO Supporting Tables

CREATE TABLE compliance_obligation (
  obligation_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  obligation_name TEXT         NOT NULL,
  statutory_act   VARCHAR(80),
                  -- EPF_ACT | ESIC_ACT | INCOME_TAX | GRATUITY_ACT | BONUS_ACT |
                  -- MATERNITY_ACT | POSH_ACT | MIN_WAGES_ACT | FACTORIES_ACT |
                  -- SHOPS_EST_ACT | LABOUR_WELFARE_FUND | OTHER
  category        VARCHAR(50),
  period_start    DATE,
  period_end      DATE,
  deadline        DATE         NOT NULL,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                  -- PENDING | IN_PROGRESS | COMPLETE | OVERDUE
  filing_reference VARCHAR(100),  -- challan number, acknowledgement ID
  submitted_by    UUID         REFERENCES oa_user(oa_user_id),
  document_id     UUID         REFERENCES document(document_id),  -- proof of filing
  headcount       INTEGER,                                         -- employees covered
  overdue_since   DATE,         -- set by StatutoryComplianceWorkflow when deadline passes
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_compliance_tenant  ON compliance_obligation(tenant_id, deadline);
CREATE INDEX idx_compliance_act     ON compliance_obligation(tenant_id, statutory_act, deadline);
CREATE INDEX idx_compliance_overdue ON compliance_obligation(tenant_id, deadline)
  WHERE status IN ('PENDING', 'OVERDUE');

-- Populated nightly by InsightService — stores percentiles/aggregates, never individual ₹ figures.
CREATE TABLE insight_cache (
  cache_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id),
  cache_key         TEXT         NOT NULL,
  period_month      DATE,
  payroll_total_inr BIGINT,
  employee_count    INTEGER,
  band_label        TEXT,
  cache_value       JSONB,
  computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at        TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_insight_cache_key ON insight_cache(tenant_id, cache_key, period_month NULLS FIRST);
CREATE INDEX idx_insight_cache_tenant ON insight_cache(tenant_id, cache_key);

CREATE TABLE storage_request (
  request_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  current_gb      INTEGER      NOT NULL,
  requested_gb    INTEGER      NOT NULL,
  reason          TEXT,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  requested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  decided_by      UUID,
  decided_at      TIMESTAMPTZ
);
CREATE INDEX idx_storage_req_status ON storage_request(status, requested_at DESC);

-- Layer 13: CHRO Reports
-- On-demand PDF report metadata; PDF is re-generated from stored row data.
CREATE TABLE chro_report (
  report_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID         NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  title        TEXT         NOT NULL,
  report_type  VARCHAR(50)  NOT NULL,  -- VAULT_HEALTH | QUARTERLY | CUSTOM
  report_data  JSONB        NOT NULL,  -- {"rows": [...]}
  generated_by UUID         REFERENCES oa_user(oa_user_id),
  generated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at   TIMESTAMPTZ             -- NULL = permanent
);

CREATE INDEX idx_chro_report_tenant ON chro_report(tenant_id, generated_at DESC);
