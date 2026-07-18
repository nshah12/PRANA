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
                       -- PENDING_ACTIVATION | ACTIVE | LOCKED | SUSPENDED | MERGED
  force_reset         BOOLEAN      DEFAULT FALSE,
  failed_totp_count   SMALLINT     DEFAULT 0,           -- Lock at 5
  last_login_at       TIMESTAMPTZ,
  activated_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  merged_into         UUID         REFERENCES employee_user(employee_user_id),
                       -- Set when this row is a duplicate merged into a canonical
                       -- employee_user_id (PA employee-merge tool). status='MERGED'.
  CONSTRAINT chk_eu_login_handle CHECK (
    mobile IS NOT NULL OR email IS NOT NULL OR status = 'PENDING_ACTIVATION'
  )
);
CREATE INDEX idx_eu_pan_token ON employee_user(pan_token);
CREATE INDEX idx_eu_mobile    ON employee_user(mobile) WHERE mobile IS NOT NULL;
CREATE INDEX idx_eu_email     ON employee_user(email)  WHERE email  IS NOT NULL;
CREATE INDEX idx_eu_merged_into ON employee_user(merged_into) WHERE merged_into IS NOT NULL;

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
-- PRE_EXIT_BULK anomaly lookahead (migration 042): fast scan for employees exiting soon.
CREATE INDEX idx_em_tenant_dol ON employee_master(tenant_id, dol) WHERE dol IS NOT NULL;
CREATE INDEX idx_emp_pan_token ON employee_master(pan_token);
-- Resolution Ladder 3 — trigram name search:
CREATE INDEX idx_emp_name_trgm ON employee_master USING GIN (full_name gin_trgm_ops);
-- Resolution Ladder 4 — cosine similarity embedding search:
-- No ANN index: this environment's pgvector build (0.4.4-yb-1.1) supports
-- neither ivfflat nor hnsw access methods. Falls back to a sequential scan,
-- which is fine at current data volume; revisit when a pgvector build with
-- a supported ANN index type is available.

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

-- employee_insight — per-employee LLM-derived insight storage (migration
-- 047_employee_insight.sql). One row per (employee_uuid, insight_type).
-- insights is JSONB and, per the privacy contract, must never contain raw ₹
-- figures, PAN, or NIK.
CREATE TABLE employee_insight (
  insight_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_uuid UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  tenant_id     UUID         REFERENCES tenant(tenant_id),
  insight_type  VARCHAR(20)  NOT NULL CHECK (insight_type IN ('CAREER', 'SKILL_GAP', 'MARKET_COMP')),
  insights      JSONB        NOT NULL DEFAULT '{}',
  computed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_employee_insight_type ON employee_insight(employee_uuid, insight_type);

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
-- idx_lal_ip: skipped -- YugabyteDB does not support an index with INET as the
-- leading (hash) column ("INDEX on column of type 'INET' not yet supported").
-- Sequential scan on ip_address is fine at current data volume.
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
  original_filename    TEXT,        -- Original filename from upload (not stored on S3)
  -- Added by migrations/033_document_statutory_hold.sql — DPDP Act erasure requests
  -- can conflict with Indian labour law retention obligations (EPF Act, Income Tax
  -- Act, Companies Act, Gratuity Act); these columns let ComplianceService.execute_erasure
  -- honour a statutory hold instead of deleting the document outright.
  statutory_hold_reason VARCHAR(50),
  statutory_hold_until  DATE,
  statutory_hold_set_at TIMESTAMPTZ,
  statutory_hold_set_by VARCHAR(50), -- 'SYSTEM_INFER' or an oa_user_id (manual override)
  employee_visible      BOOLEAN      NOT NULL DEFAULT TRUE,
  employer_visible      BOOLEAN      NOT NULL DEFAULT TRUE,
  -- Added by migrations/044_document_legal_hold.sql — an indefinite litigation
  -- hold, distinct from statutory_hold_until (a KNOWN-expiry labour-law date).
  legal_hold_active     BOOLEAN      NOT NULL DEFAULT FALSE,
  legal_hold_reason     TEXT
);
CREATE INDEX idx_doc_pan_token ON document(pan_token) WHERE is_deleted = FALSE;
CREATE INDEX idx_doc_pipeline  ON document(pipeline_status) WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION');
CREATE INDEX idx_doc_employee  ON document(employee_uuid, doc_type);
CREATE INDEX idx_doc_tenant    ON document(tenant_id, pipeline_status);
CREATE INDEX idx_doc_statutory_hold ON document(statutory_hold_until)
  WHERE statutory_hold_until IS NOT NULL AND is_deleted = FALSE AND employer_visible = TRUE;
CREATE INDEX idx_doc_legal_hold ON document(legal_hold_active) WHERE legal_hold_active = TRUE;
CREATE INDEX idx_doc_extracted ON document USING GIN (extracted_fields);

-- Deferred FK: career_event → document
ALTER TABLE career_event
  ADD CONSTRAINT fk_ce_doc
  FOREIGN KEY (doc_uuid) REFERENCES document(document_id);

-- Batch-level summary for multi-file uploads (BatchProgressWorkflow, migration 043).
-- One row per batch_id, created at upload time, updated by write_batch_summary once
-- all child DocumentPipelineWorkflow runs (or the batch timeout) settle.
CREATE TABLE document_batch (
  batch_id      UUID         PRIMARY KEY,
  tenant_id     UUID         NOT NULL REFERENCES tenant(tenant_id),
  total_files   INTEGER      NOT NULL DEFAULT 0,
  routed        INTEGER      NOT NULL DEFAULT 0,
  exceptions    INTEGER      NOT NULL DEFAULT 0,
  quarantined   INTEGER      NOT NULL DEFAULT 0,
  failed        INTEGER      NOT NULL DEFAULT 0,
  status        VARCHAR(20)  NOT NULL DEFAULT 'PROCESSING',
                 -- PROCESSING | COMPLETE | PARTIAL
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMPTZ
);
CREATE INDEX idx_document_batch_tenant ON document_batch(tenant_id, created_at DESC);

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

-- SHARE_ENUM anomaly signal (migration 042) — no record of a failed share-link OTP
-- attempt existed anywhere before this table.
CREATE TABLE share_otp_attempt (
    attempt_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id       UUID         NOT NULL REFERENCES share_token(token_id),
    ip_address     INET         NOT NULL,
    success        BOOLEAN      NOT NULL,
    attempted_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
-- idx_share_otp_attempt_ip: skipped -- same YugabyteDB INET-index limitation as idx_lal_ip above.
CREATE INDEX idx_share_otp_attempt_token ON share_otp_attempt(token_id, attempted_at DESC);

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
-- idx_dal_ip: skipped -- same YugabyteDB INET-index limitation as idx_lal_ip above.
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
  event_id       UUID         DEFAULT gen_random_uuid(),
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
  occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (event_id, occurred_at)
  -- Composite PK (not event_id alone): YugabyteDB/Postgres require the partition
  -- column in every PK/unique constraint on a partitioned table. A single-column
  -- PK here made this CREATE TABLE fail outright on every fresh db-init — the
  -- table silently never existed. Fixed 2026-07-18 after tracing a live 500 on
  -- /admin/tenants back through a chain of never-applied migrations.
) PARTITION BY RANGE (occurred_at);
-- Monthly partitions: audit_event_2025_01, audit_event_2025_02, ...
-- Hot in YugabyteDB. Cold to Apache Iceberg on S3 via RetentionWorkflow after 30 days.
-- Retained hot for 7 years minimum (DPDP Act S.9). Never deleted from cold storage.
-- Append-only by policy — REVOKE UPDATE, DELETE ON audit_event FROM prana_app_role is
-- real, executed DDL at the bottom of this file (LAYER 14), not just a comment.
CREATE INDEX idx_audit_type   ON audit_event(event_type, occurred_at DESC);
CREATE INDEX idx_audit_actor  ON audit_event(actor_type, actor_id, occurred_at DESC);
CREATE INDEX idx_audit_tenant ON audit_event(tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_pan    ON audit_event(pan_token, occurred_at DESC);
CREATE INDEX idx_audit_doc    ON audit_event(document_id, occurred_at DESC);
CREATE TABLE audit_event_2025   PARTITION OF audit_event FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE audit_event_2026   PARTITION OF audit_event FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE audit_event_2027   PARTITION OF audit_event FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE audit_event_default PARTITION OF audit_event DEFAULT;
-- A partitioned parent with zero partitions rejects every INSERT ("no partition
-- of relation found for row") — dev/test needs at least these to actually work.
-- RetentionWorkflow manages real monthly partitions in production.

-- Added by migrations/045_audit_archive_log.sql — records which audit_event rows
-- were copied to cold S3 storage. Cannot be a column on audit_event itself: UPDATE
-- is REVOKEd on that table (see LAYER 14 below) so this is deliberately a separate,
-- INSERT-only bookkeeping table.
CREATE TABLE audit_archive_log (
  event_id     UUID         PRIMARY KEY,
  archived_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  s3_key       TEXT         NOT NULL
);
CREATE INDEX idx_audit_archive_log_archived_at ON audit_archive_log(archived_at);

CREATE TABLE anomaly_event (
  anomaly_id     UUID         DEFAULT gen_random_uuid(),
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
  detected_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (anomaly_id, detected_at)
  -- Composite PK — see audit_event's identical fix above for why.
) PARTITION BY RANGE (detected_at);
-- Severity: P0 = immediate PA page; P1 = 1hr war room; P2 = next-business-day; P3 = weekly digest
-- P0 breach triggers BreachNotificationWorkflow: 72-hour DPB notification (DPDP Act S.35 STATUTORY)
CREATE INDEX idx_anomaly_open ON anomaly_event(tenant_id, detected_at DESC) WHERE status = 'OPEN';
CREATE TABLE anomaly_event_2025   PARTITION OF anomaly_event FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE anomaly_event_2026   PARTITION OF anomaly_event FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE anomaly_event_2027   PARTITION OF anomaly_event FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE anomaly_event_default PARTITION OF anomaly_event DEFAULT;

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
CREATE TABLE kms_key_log_2025   PARTITION OF kms_key_log FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE kms_key_log_2026   PARTITION OF kms_key_log FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE kms_key_log_2027   PARTITION OF kms_key_log FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE kms_key_log_default PARTITION OF kms_key_log DEFAULT;

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
CREATE TABLE pa_platform_summary_0 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE pa_platform_summary_1 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE pa_platform_summary_2 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE pa_platform_summary_3 PARTITION OF pa_platform_summary FOR VALUES WITH (MODULUS 4, REMAINDER 3);
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
  ('refresh_token_ttl_days',            '7',           'DURATION_DAYS',    'JWT refresh token TTL', '1', '30'),
  ('audit_integrity_check_interval_minutes', '60',     'DURATION_MINUTES', 'AuditIntegrityVerificationWorkflow schedule cadence', '15', '1440'),
  ('off_hours_start_hour',               '22',          'INTEGER',           'OFF_HOURS_ACCESS: start of after-hours window, IST 24h clock', '0', '23'),
  ('off_hours_end_hour',                 '6',           'INTEGER',           'OFF_HOURS_ACCESS: end of after-hours window, IST 24h clock', '0', '23'),
  ('impossible_travel_speed_kmh',        '900',         'INTEGER',           'IMPOSSIBLE_TRAVEL: speed above which two logins are implausible (roughly commercial flight speed)', '200', '5000'),
  ('pre_exit_bulk_lookahead_days',       '30',          'DURATION_DAYS',     'PRE_EXIT_BULK: how far in advance a recorded exit date (employee_master.dol) counts as "upcoming"', '1', '90'),
  ('bulk_access_auto_lock_enabled',      'false',       'BOOLEAN',           'Auto-lock the account on a BULK_DOC_ACCESS anomaly — ships OFF, PA opt-in after trusting real thresholds', 'false', 'true'),
  ('brute_force_auto_lock_enabled',      'false',       'BOOLEAN',           'Auto-lock the account on a BRUTE_FORCE anomaly — ships OFF, PA opt-in after trusting real thresholds', 'false', 'true'),
  ('policy_lock_default_hours',          '24',          'DURATION_HOURS',    'PolicyLockWorkflow default lock duration when auto-lock is enabled', '1', '168'),
  ('platform_anomaly_check_minutes',     '5',           'DURATION_MINUTES',  'AnomalyDetectionWorkflow batch-scan interval', '1', '60'),
  ('pipeline_max_duration_hours',        '4',           'DURATION_HOURS',    'BatchTimeoutMonitorWorkflow: per-file ceiling before a document is marked a straggler', '1', '24'),
  ('batch_max_duration_hours',           '24',          'DURATION_HOURS',    'BatchProgressWorkflow: whole-batch ceiling before remaining unfinished files are marked stragglers', '1', '168');

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

-- webhook_delivery_log — durable delivery record for WebhookDeliveryWorkflow
-- (workflows/platform_ops.py, migration 046_webhook_delivery_log.sql)
CREATE TABLE webhook_delivery_log (
  delivery_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         REFERENCES tenant(tenant_id),
  webhook_url     TEXT         NOT NULL,
  event_type      VARCHAR(60)  NOT NULL,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                   -- PENDING | DELIVERED | FAILED
  response_code   SMALLINT,
  attempt_count   SMALLINT     NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_webhook_delivery_tenant ON webhook_delivery_log(tenant_id, created_at DESC);
CREATE INDEX idx_webhook_delivery_failed ON webhook_delivery_log(status) WHERE status = 'FAILED';

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

-- ============================================================
-- LAYER 13: INCIDENT SEVERITY & SLA POLICY (migration 041)
-- ============================================================
-- PA-editable replacement for hardcoded severity/SLA constants formerly scattered across
-- services/incident_service.py, services/error_threshold_service.py, services/health_service.py,
-- and workflows/activities.py + kafka consumers. See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md.

CREATE TABLE sla_policy (
    severity              VARCHAR(2)   PRIMARY KEY,          -- P0 | P1 | P2 | P3
    sla_minutes            INTEGER      NOT NULL,
    auto_create_incident   BOOLEAN      NOT NULL DEFAULT FALSE,
    description              TEXT,
    updated_by                UUID,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One small rule engine, reused across all three severity-deciding domains. See
-- services/severity_policy_service.py for the evaluation algorithm and
-- prana-db/migrations/041_severity_sla_policy.sql for the full explanation of
-- occurrence_threshold vs occurrence_threshold_max semantics.
CREATE TABLE severity_classification_rule (
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
CREATE INDEX idx_severity_rule_domain ON severity_classification_rule(domain, priority)
    WHERE is_active = TRUE;

INSERT INTO sla_policy (severity, sla_minutes, auto_create_incident, description) VALUES
    ('P0', 30,   TRUE,  'Immediate — security/DPDP breach class, PA paged'),
    ('P1', 240,  TRUE,  'Urgent — war room within 4 hours'),
    ('P2', 1440, FALSE, 'Next business day'),
    ('P3', 4320, FALSE, 'Weekly digest tier');

INSERT INTO severity_classification_rule
    (domain, match_type, match_value, occurrence_threshold, occurrence_threshold_max, window_minutes, severity, priority, description) VALUES
    ('ERROR_OBSERVABILITY', 'PREFIX', '/auth/',                 NULL, NULL, NULL, 'P1', 10, 'Security-critical HTTP path'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/totp/',                 NULL, NULL, NULL, 'P1', 10, 'Security-critical HTTP path'),
    ('ERROR_OBSERVABILITY', 'EXACT',  'AuthConsumer',           NULL, NULL, NULL, 'P1', 10, 'Security-critical Kafka consumer'),
    ('ERROR_OBSERVABILITY', 'EXACT',  'verify_audit_integrity', NULL, NULL, NULL, 'P1', 10, 'Security-critical Temporal activity'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/v1/dpdp/',               3, NULL,   10, 'P2', 20, 'Compliance-critical endpoint, recurring'),
    ('ERROR_OBSERVABILITY', 'PREFIX', '/v1/ingest/',             3, NULL,   10, 'P2', 20, 'Compliance-critical endpoint, recurring'),
    ('ERROR_OBSERVABILITY', 'DEFAULT', NULL,                     1,    1, NULL, 'P2', 90, 'Novel bug, first occurrence'),
    ('ERROR_OBSERVABILITY', 'DEFAULT', NULL,                    10, NULL,   15, 'P3', 95, 'Noisy recurrence, systemic breakage signal');

INSERT INTO severity_classification_rule
    (domain, match_type, match_value, severity, priority, description) VALUES
    ('HEALTH_CHECK', 'EXACT', 'prana-api', 'P1', 10, 'CPU service down — REST + Temporal'),
    ('HEALTH_CHECK', 'EXACT', 'prana-ai',  'P2', 10, 'GPU pipeline worker down'),
    ('HEALTH_CHECK', 'EXACT', 'prana-ask', 'P3', 10, 'GPU chatbot worker down');

INSERT INTO severity_classification_rule
    (domain, match_type, match_value, occurrence_threshold, window_minutes, severity, priority, description) VALUES
    ('ANOMALY_RULE', 'EXACT', 'CROSS_TENANT_UPLOAD_ATTEMPT', NULL, NULL, 'P0', 10, 'Document upload resolved to a different tenant''s employee'),
    ('ANOMALY_RULE', 'EXACT', 'CROSS_TENANT_QUERY',          NULL, NULL, 'P0', 10, 'Blocked attempt to read another tenant''s resource by ID'),
    ('ANOMALY_RULE', 'EXACT', 'IMPOSSIBLE_TRAVEL',           NULL, NULL, 'P0', 15, 'Two logins imply travel speed exceeding plausibility'),
    ('ANOMALY_RULE', 'EXACT', 'PRIVILEGE_ESCALATION',        NULL, NULL, 'P1', 20, 'Self-escalation or jump to a higher-privilege role'),
    ('ANOMALY_RULE', 'EXACT', 'BRUTE_FORCE',                    5,   15, 'P1', 30, 'Repeated failed login attempts, same identifier'),
    ('ANOMALY_RULE', 'EXACT', 'BULK_DOC_ACCESS',                50,  10, 'P1', 30, 'Unusually high document access volume, same actor'),
    ('ANOMALY_RULE', 'EXACT', 'PRE_EXIT_BULK',                  20, 1440, 'P1', 30, 'Bulk self-access shortly before a recorded exit date'),
    ('ANOMALY_RULE', 'EXACT', 'SHARE_ENUM',                      5,   10, 'P2', 40, 'Failed OTP attempts against many distinct share tokens, same IP'),
    ('ANOMALY_RULE', 'EXACT', 'OFF_HOURS_ACCESS',              NULL, NULL, 'P2', 50, 'OA actor document access outside business hours'),
    ('ANOMALY_RULE', 'DEFAULT', NULL,                          NULL, NULL, 'P3', 99, 'Fallback for any unrecognized anomaly rule_name');

-- ============================================================
-- LAYER 15: RECONCILIATION (2026-07-18)
-- ============================================================
-- prana-db/migrations/ had drifted from this file for a long time: schema.sql
-- was edited directly as features shipped, while most migration files were
-- never actually replayed against a real database (no runner ever existed).
-- This surfaced as a live 500 on GET /admin/tenants?status_filter=PENDING
-- (tenant.industry didn't exist) and GET /admin/incidents (service_incident
-- didn't exist). Reconciled by diffing the live, working DB (after applying
-- every migration that still applied cleanly) against this file table-by-
-- table and column-by-column. Everything below is additive and idempotent.
-- The migrations/ directory is now historical reference only — see its
-- README for the full per-file reconciliation notes.

-- ── Tenant enterprise profile (migrations 007/016) ─────────────────────────
ALTER TABLE tenant
  ADD COLUMN IF NOT EXISTS brand_name                 VARCHAR(200),
  ADD COLUMN IF NOT EXISTS entity_type                VARCHAR(30),
  ADD COLUMN IF NOT EXISTS pan_entity                 VARCHAR(10),
  ADD COLUMN IF NOT EXISTS tan                        VARCHAR(10),
  ADD COLUMN IF NOT EXISTS incorporation_date         DATE,
  ADD COLUMN IF NOT EXISTS roc_jurisdiction           VARCHAR(50),
  ADD COLUMN IF NOT EXISTS reg_address                JSONB,
  ADD COLUMN IF NOT EXISTS corp_address                JSONB,
  ADD COLUMN IF NOT EXISTS primary_contact            JSONB,
  ADD COLUMN IF NOT EXISTS dpo_name                   VARCHAR(100),
  ADD COLUMN IF NOT EXISTS dpo_email                  VARCHAR(150),
  ADD COLUMN IF NOT EXISTS grievance_officer_name     VARCHAR(100),
  ADD COLUMN IF NOT EXISTS grievance_officer_email    VARCHAR(150),
  ADD COLUMN IF NOT EXISTS dpa_accepted_at            TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS dpa_version                VARCHAR(20) DEFAULT '1.0',
  ADD COLUMN IF NOT EXISTS industry                   VARCHAR(50),
  ADD COLUMN IF NOT EXISTS employee_headcount_band    VARCHAR(20),
  ADD COLUMN IF NOT EXISTS payroll_frequency          VARCHAR(20) DEFAULT 'MONTHLY',
  ADD COLUMN IF NOT EXISTS fiscal_year_start          VARCHAR(10) DEFAULT 'APRIL',
  ADD COLUMN IF NOT EXISTS hrms_system                VARCHAR(50),
  ADD COLUMN IF NOT EXISTS document_ingestion_method  VARCHAR(30) DEFAULT 'PORTAL_UPLOAD',
  ADD COLUMN IF NOT EXISTS additional_domains         TEXT[],
  ADD COLUMN IF NOT EXISTS pf_registration            VARCHAR(30),
  ADD COLUMN IF NOT EXISTS esic_registration          VARCHAR(20),
  ADD COLUMN IF NOT EXISTS logo_url                   TEXT,
  ADD COLUMN IF NOT EXISTS brand_colour               VARCHAR(7),
  ADD COLUMN IF NOT EXISTS support_email              VARCHAR(150),
  ADD COLUMN IF NOT EXISTS sla_tier                   VARCHAR(20) DEFAULT 'STANDARD',
  ADD COLUMN IF NOT EXISTS onboarding_tier            VARCHAR(20) DEFAULT 'ASSISTED',
  ADD COLUMN IF NOT EXISTS contract_type              VARCHAR(20) DEFAULT 'ANNUAL',
  ADD COLUMN IF NOT EXISTS account_manager            VARCHAR(100);

-- ── career_event insight metadata (migration 004) ──────────────────────────
ALTER TABLE career_event
  ADD COLUMN IF NOT EXISTS insight_generated_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS insight_model_version  VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_career_event_insight_stale
  ON career_event(insight_generated_at)
  WHERE insight_text IS NULL OR insight_generated_at IS NULL;

-- ── employee_consent per-org scoping (migration 026) ───────────────────────
ALTER TABLE employee_consent
  ADD COLUMN IF NOT EXISTS tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS share_mobile    BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS share_email     BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS notice_language CHAR(5) NOT NULL DEFAULT 'en',
  ADD COLUMN IF NOT EXISTS notice_hash     VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_consent_global  ON employee_consent(employee_user_id, purpose) WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_consent_per_org  ON employee_consent(employee_user_id, purpose, tenant_id) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_consent_tenant_purpose ON employee_consent(tenant_id, purpose, is_active) WHERE tenant_id IS NOT NULL;

-- ── compliance_obligation audit-grade fields (migrations 002/014/019) ──────
ALTER TABLE compliance_obligation
  ADD COLUMN IF NOT EXISTS statutory_act       VARCHAR(80),
  ADD COLUMN IF NOT EXISTS category            VARCHAR(50),
  ADD COLUMN IF NOT EXISTS period_start        DATE,
  ADD COLUMN IF NOT EXISTS period_end          DATE,
  ADD COLUMN IF NOT EXISTS filing_reference    VARCHAR(100),
  ADD COLUMN IF NOT EXISTS submitted_by        UUID REFERENCES oa_user(oa_user_id),
  ADD COLUMN IF NOT EXISTS document_id         UUID REFERENCES document(document_id),
  ADD COLUMN IF NOT EXISTS headcount           INTEGER,
  ADD COLUMN IF NOT EXISTS overdue_since       DATE,
  ADD COLUMN IF NOT EXISTS obligation_type     VARCHAR(50),
  ADD COLUMN IF NOT EXISTS statutory_ref       VARCHAR(100),
  ADD COLUMN IF NOT EXISTS period              VARCHAR(20),
  ADD COLUMN IF NOT EXISTS completion_pct      INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_employees     INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS compliant_employees INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gap_count           INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS notes               TEXT,
  ADD COLUMN IF NOT EXISTS last_computed_at    TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_compob_overdue ON compliance_obligation(tenant_id) WHERE status = 'OVERDUE';
CREATE INDEX IF NOT EXISTS idx_compob_type    ON compliance_obligation(tenant_id, obligation_type) WHERE obligation_type IS NOT NULL;

-- ── PA CHRO alert config + audit archival config (migrations 014/045) ─────
INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value) VALUES
  ('chro_alert_deadline_alert',      'true', 'BOOLEAN', 'CHRO: notify when statutory deadline < 30 days away', NULL, NULL),
  ('chro_alert_vault_health_drop',   'true', 'BOOLEAN', 'CHRO: notify when org vault health drops > 5 points', NULL, NULL),
  ('chro_alert_exception_spike',     'true', 'BOOLEAN', 'CHRO: notify when exception queue exceeds 5 open', NULL, NULL),
  ('chro_alert_exit_doc_delay',      'true', 'BOOLEAN', 'CHRO: notify when exit docs not pushed within 7 days', NULL, NULL),
  ('audit_archival_cutoff_days',     '730',  'DURATION_DAYS', 'AuditArchivalWorkflow: age (days) after which audit_event rows are copied to cold S3 storage.', '30', '2555'),
  ('audit_archival_batch_size',      '5000', 'INTEGER', 'AuditArchivalWorkflow: max rows archived per activity execution.', '100', '50000')
ON CONFLICT (config_key) DO NOTHING;

-- ── HRMS connector definition (PA-level catalogue) — migration 029 ─────────
CREATE TABLE IF NOT EXISTS hrms_connector_definition (
  connector_definition_id UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_key           VARCHAR(30)  NOT NULL UNIQUE,   -- SAP | DARWINBOX | KEKA | GREYTHR | ZOHO | ...
  display_name            VARCHAR(100) NOT NULL,
  logo_url                TEXT,
  auth_method             VARCHAR(20)  NOT NULL,          -- API_KEY | OAUTH2 | HMAC
  supported_modes         TEXT[]       NOT NULL DEFAULT ARRAY['PULL'],  -- PULL | PUSH | WEBHOOK
  canonical_field_schema  JSONB        NOT NULL DEFAULT '{}',
  docs_url                TEXT,
  is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hrms_def_key    ON hrms_connector_definition(connector_key);
CREATE INDEX IF NOT EXISTS idx_hrms_def_active ON hrms_connector_definition(is_active);

ALTER TABLE hrms_connector_config
  ADD COLUMN IF NOT EXISTS connector_definition_id UUID REFERENCES hrms_connector_definition(connector_definition_id),
  ADD COLUMN IF NOT EXISTS field_mapping           JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS webhook_secret           TEXT;  -- HMAC secret for validating inbound webhooks; plaintext OK, low-sensitivity shared secret

CREATE TABLE IF NOT EXISTS hrms_sync_log (
  sync_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_id    UUID         NOT NULL REFERENCES hrms_connector_config(connector_id),
  tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
  sync_mode       VARCHAR(20)  NOT NULL DEFAULT 'PULL',
  started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  status          VARCHAR(20)  NOT NULL DEFAULT 'RUNNING',  -- RUNNING | SUCCESS | FAILED
  docs_pushed     INTEGER      NOT NULL DEFAULT 0,
  docs_failed     INTEGER      NOT NULL DEFAULT 0,
  error_message   TEXT,
  cursor_before   TEXT,
  cursor_after    TEXT,
  temporal_run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_hrms_sync_connector ON hrms_sync_log(connector_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_hrms_sync_tenant    ON hrms_sync_log(tenant_id, started_at DESC);

-- ── incident + error_event — platform incident tracking (migrations 017/040) ─
-- incident: PA/CISO-visible security & SLA incidents. error_event: application
-- error observability, promoted to `incident` rows by ErrorThresholdEvaluationWorkflow.
CREATE TABLE IF NOT EXISTS incident (
  incident_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID         REFERENCES tenant(tenant_id),
  incident_type   VARCHAR(40)  NOT NULL,
  severity        VARCHAR(5)   NOT NULL,             -- P0 | P1 | P2 | P3
  title           TEXT         NOT NULL,
  description     TEXT,
  source_table    VARCHAR(40),
  source_id       UUID,
  assigned_to     UUID,
  assigned_role   VARCHAR(20),
  status          VARCHAR(20)  NOT NULL DEFAULT 'OPEN',  -- OPEN | ACKNOWLEDGED | ESCALATED | RESOLVED
  sla_deadline    TIMESTAMPTZ,
  escalated_at    TIMESTAMPTZ,
  resolved_at     TIMESTAMPTZ,
  resolved_by     UUID,
  resolution_note TEXT,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_incident_open_severity ON incident(severity, created_at DESC) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_incident_sla           ON incident(sla_deadline) WHERE status != 'RESOLVED';
CREATE INDEX IF NOT EXISTS idx_incident_tenant_status ON incident(tenant_id, status, severity);

CREATE TABLE IF NOT EXISTS error_event (
  error_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint        VARCHAR(64)  NOT NULL,   -- hash of (exception_type, source, source_detail) for dedup
  exception_type     VARCHAR(200) NOT NULL,
  message            TEXT,
  traceback          TEXT,
  source             VARCHAR(30)  NOT NULL,   -- HTTP | KAFKA | TEMPORAL
  source_detail      VARCHAR(200),
  request_id         UUID,
  event_id           UUID,
  tenant_id          UUID         REFERENCES tenant(tenant_id),
  actor_type         VARCHAR(30),
  actor_id           UUID,
  occurrence_count   INTEGER      NOT NULL DEFAULT 1,
  first_seen_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_seen_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  status             VARCHAR(20)  NOT NULL DEFAULT 'NEW',  -- NEW | ACKNOWLEDGED | PROMOTED | RESOLVED
  linked_incident_id UUID         REFERENCES incident(incident_id),
  resolved_by        UUID,
  resolved_at        TIMESTAMPTZ,
  resolution_note    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_error_event_fingerprint_open
  ON error_event(fingerprint) WHERE status IN ('NEW', 'ACKNOWLEDGED');
CREATE INDEX IF NOT EXISTS idx_error_event_status     ON error_event(status, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_event_last_seen  ON error_event(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_event_tenant     ON error_event(tenant_id, last_seen_at DESC) WHERE tenant_id IS NOT NULL;

-- ── notification_log — every outbound notification with delivery tracking (migration 017) ─
CREATE TABLE IF NOT EXISTS notification_log (
  notification_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID         REFERENCES tenant(tenant_id),   -- NULL for platform-level notifs
  event_type       VARCHAR(40)  NOT NULL,     -- ANOMALY_DETECTED | DOC_ROUTED | ...
  source_id        UUID,
  source_table     VARCHAR(40),
  recipient_id     UUID         NOT NULL,
  recipient_type   VARCHAR(20)  NOT NULL,     -- EMPLOYEE | OA_USER | PORTAL_ADMIN
  recipient_email  TEXT,
  recipient_phone  TEXT,
  channel          VARCHAR(20)  NOT NULL,     -- EMAIL | SMS | WHATSAPP | PUSH | PORTAL_BELL
  template_id      VARCHAR(50)  NOT NULL,
  template_data    JSONB,
  status           VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',  -- QUEUED | SENT | FAILED
  provider_ref     TEXT,
  sent_at          TIMESTAMPTZ,
  failed_at        TIMESTAMPTZ,
  error_message    TEXT,
  retry_count      SMALLINT     NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_log_tenant_created  ON notification_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_log_recipient       ON notification_log(recipient_id, channel, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_log_queued_failed   ON notification_log(status) WHERE status IN ('QUEUED', 'FAILED');
CREATE INDEX IF NOT EXISTS idx_notif_log_event_type      ON notification_log(event_type, created_at DESC);

-- ── Public-facing submission tables (migration 008) ────────────────────────
CREATE TABLE IF NOT EXISTS contact_inquiry (
  id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(150) NOT NULL,
  org           VARCHAR(200),
  enquiry_type  VARCHAR(50),
  message       TEXT,
  status        VARCHAR(20)  NOT NULL DEFAULT 'NEW',   -- NEW | REVIEWED | REPLIED
  ip_address    INET,
  submitted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contact_inquiry_submitted ON contact_inquiry(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_contact_inquiry_status    ON contact_inquiry(status);

CREATE TABLE IF NOT EXISTS self_service_application (
  id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name        VARCHAR(200) NOT NULL,
  domain          VARCHAR(100) NOT NULL,
  entity_type     VARCHAR(50),
  industry        VARCHAR(50),
  headcount_band  VARCHAR(20),
  contact_name    VARCHAR(100) NOT NULL,
  contact_email   VARCHAR(150) NOT NULL,
  contact_mobile  VARCHAR(20),
  message         TEXT,
  how_heard       VARCHAR(50),
  agreed_to_dpa   BOOLEAN      NOT NULL DEFAULT FALSE,
  email_verified  BOOLEAN      NOT NULL DEFAULT FALSE,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING', -- PENDING | REVIEWED | APPROVED | REJECTED
  review_notes    TEXT,
  submitted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  reviewed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ssa_submitted ON self_service_application(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_ssa_status    ON self_service_application(status);
CREATE INDEX IF NOT EXISTS idx_ssa_email     ON self_service_application(contact_email);

CREATE TABLE IF NOT EXISTS org_registration_otp (
  token       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  email       VARCHAR(150) NOT NULL,
  otp_hash    VARCHAR(64)  NOT NULL,   -- SHA-256(otp) — never store plaintext
  form_data   JSONB,
  expires_at  TIMESTAMPTZ  NOT NULL,
  verified    BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reg_otp_email ON org_registration_otp(email);

-- ── device_registration — mobile trust-based biometric auth (migration 012) ─
CREATE TABLE IF NOT EXISTS device_registration (
  device_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id    UUID         NOT NULL REFERENCES employee_user(employee_user_id) ON DELETE CASCADE,
  platform            VARCHAR(10)  NOT NULL CHECK (platform IN ('ANDROID', 'IOS')),
  device_name         VARCHAR(100),
  device_fingerprint  VARCHAR(128),
  push_token          TEXT,
  biometric_enrolled  BOOLEAN      NOT NULL DEFAULT FALSE,
  enrolled_at         TIMESTAMPTZ,
  last_used_at        TIMESTAMPTZ,
  registered_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  revoked             BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_dr_employee    ON device_registration(employee_user_id) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_dr_fingerprint ON device_registration(device_fingerprint) WHERE revoked = FALSE;

-- ── doc_type_field_manifest — OA-configurable per-doc-type field mapping (migration 018) ─
CREATE TABLE IF NOT EXISTS doc_type_field_manifest (
  manifest_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              UUID         REFERENCES tenant(tenant_id) ON DELETE CASCADE,  -- NULL = platform default
  doc_type               VARCHAR(50)  NOT NULL,
  required_fields        JSONB        NOT NULL DEFAULT '[]',
  identity_fields        JSONB        NOT NULL DEFAULT '[]',
  optional_fields        JSONB        NOT NULL DEFAULT '[]',
  classification_signals JSONB        NOT NULL DEFAULT '[]',
  confidence_threshold   DOUBLE PRECISION NOT NULL DEFAULT 0.75 CHECK (confidence_threshold BETWEEN 0.0 AND 1.0),
  supported_formats      JSONB        NOT NULL DEFAULT '["pdf", "docx", "jpeg", "jpg", "png", "tiff"]',
  is_active              BOOLEAN      NOT NULL DEFAULT TRUE,
  created_by             UUID         REFERENCES oa_user(oa_user_id),
  created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_by             UUID         REFERENCES oa_user(oa_user_id),
  usage_count            INTEGER      NOT NULL DEFAULT 0,
  signal_weights         JSONB        NOT NULL DEFAULT '[]'  -- migration 037: per-signal scoring weights
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_manifest_platform_doctype ON doc_type_field_manifest(doc_type) WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uidx_manifest_tenant_doctype   ON doc_type_field_manifest(tenant_id, doc_type) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_manifest_active ON doc_type_field_manifest(doc_type, is_active);
CREATE INDEX IF NOT EXISTS idx_manifest_tenant ON doc_type_field_manifest(tenant_id) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_manifest_usage  ON doc_type_field_manifest(tenant_id, usage_count DESC);

-- ── Alumni network outreach (migrations 023/025/026/027) ───────────────────
CREATE TABLE IF NOT EXISTS alumni_outreach (
  outreach_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
  employee_uuid    UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  employee_user_id UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  sent_by_oa_user  UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  subject          VARCHAR(200) NOT NULL,
  body_text        TEXT         NOT NULL CHECK (LENGTH(body_text) <= 2000),
  status           VARCHAR(20)  NOT NULL DEFAULT 'SENT'
                     CHECK (status IN ('SENT', 'READ', 'REPLIED', 'IGNORED', 'OPTED_OUT')),
  sent_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  read_at          TIMESTAMPTZ,
  replied_at       TIMESTAMPTZ,
  reply_body       TEXT         CHECK (LENGTH(reply_body) <= 2000)
);
CREATE INDEX IF NOT EXISTS idx_alumni_outreach_employee ON alumni_outreach(employee_user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alumni_outreach_tenant   ON alumni_outreach(tenant_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alumni_outreach_window   ON alumni_outreach(tenant_id, employee_user_id, sent_at DESC);

-- ── Gamification — career score, badges, streaks (migration 028) ──────────
CREATE TABLE IF NOT EXISTS badge_definition (
  badge_definition_id UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  badge_key           VARCHAR(50)  NOT NULL UNIQUE,
  badge_name          VARCHAR(100) NOT NULL,
  badge_description   TEXT,
  badge_icon          VARCHAR(10)  NOT NULL,
  category            VARCHAR(30)  NOT NULL,
  sort_order          SMALLINT     NOT NULL DEFAULT 0,
  is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_badge (
  employee_badge_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id    UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  badge_definition_id UUID         NOT NULL REFERENCES badge_definition(badge_definition_id),
  context_key         VARCHAR(50)  NOT NULL DEFAULT '',  -- disambiguates repeatable badges (e.g. per-org)
  earned_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  context             JSONB        NOT NULL DEFAULT '{}',
  UNIQUE (employee_user_id, badge_definition_id, context_key)
);
CREATE INDEX IF NOT EXISTS idx_emp_badge_user ON employee_badge(employee_user_id);

CREATE TABLE IF NOT EXISTS career_score (
  employee_user_id   UUID         PRIMARY KEY REFERENCES employee_user(employee_user_id),
  score              SMALLINT     NOT NULL DEFAULT 0,
  completeness_pts   SMALLINT     NOT NULL DEFAULT 0,
  freshness_pts      SMALLINT     NOT NULL DEFAULT 0,
  diversity_pts      SMALLINT     NOT NULL DEFAULT 0,
  engagement_pts     SMALLINT     NOT NULL DEFAULT 0,
  last_calculated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_streak (
  employee_user_id    UUID         PRIMARY KEY REFERENCES employee_user(employee_user_id),
  current_streak_days SMALLINT     NOT NULL DEFAULT 0,
  longest_streak_days SMALLINT     NOT NULL DEFAULT 0,
  last_checkin_date   DATE,
  streak_started_date DATE,
  total_checkins      INTEGER      NOT NULL DEFAULT 0,
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Comp benchmarking — opt-in contribution + k-anonymous results (migration 024) ─
-- salary_band (above, LAYER 9b/10) holds the aggregated cohort bands themselves;
-- these two tables track individual opt-in and the per-employee result view.
CREATE TABLE IF NOT EXISTS comp_contribution (
  contribution_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  pan_token        VARCHAR(64)  NOT NULL,
  cohort_key       VARCHAR(300) NOT NULL,
  contributed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  withdrawn_at     TIMESTAMPTZ,
  UNIQUE (employee_user_id, cohort_key)
);
CREATE INDEX IF NOT EXISTS idx_contrib_employee ON comp_contribution(employee_user_id);
CREATE INDEX IF NOT EXISTS idx_contrib_cohort    ON comp_contribution(cohort_key) WHERE withdrawn_at IS NULL;

CREATE TABLE IF NOT EXISTS peer_benchmark_result (
  result_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  cohort_key       VARCHAR(300) NOT NULL,
  percentile_band  VARCHAR(20),
  cohort_size      INTEGER      NOT NULL,
  suppressed       BOOLEAN      NOT NULL DEFAULT FALSE,   -- TRUE if cohort_size < CFO_COHORT_MIN
  label_text       VARCHAR(200),
  computed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (employee_user_id, cohort_key)
);
CREATE INDEX IF NOT EXISTS idx_benchmark_employee ON peer_benchmark_result(employee_user_id);

-- ── service_incident — PA infra health monitoring (migration 011) ─────────
CREATE TABLE IF NOT EXISTS service_incident (
  incident_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  service_name    VARCHAR(50)  NOT NULL,   -- prana-api | prana-ai | prana-ask | kafka | redis | db
  severity        VARCHAR(20)  NOT NULL,   -- P1 | P2 | P3
  status          VARCHAR(20)  NOT NULL DEFAULT 'OPEN',  -- OPEN | ACKNOWLEDGED | RESOLVED
  title           TEXT         NOT NULL,
  detail          TEXT,
  detected_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at TIMESTAMPTZ,
  acknowledged_by UUID,
  resolved_at     TIMESTAMPTZ,
  resolved_by     UUID,
  resolution_note TEXT,
  notified_at     TIMESTAMPTZ,
  check_url       VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS idx_service_incident_status   ON service_incident(status);
CREATE INDEX IF NOT EXISTS idx_service_incident_service  ON service_incident(service_name, status);
CREATE INDEX IF NOT EXISTS idx_service_incident_detected ON service_incident(detected_at DESC);

-- ============================================================
-- LAYER 14: SECURITY — LEAST-PRIVILEGE APPLICATION ROLE
-- ============================================================
-- The app's runtime DB pool (config.py db_user/db_password) must connect as
-- this role, never as the yugabyte/postgres superuser — otherwise the
-- audit_event REVOKE below is meaningless (the app could just use its own
-- elevated credentials to bypass it). See KAFKA_REDIS_ARCHITECTURE.md §8 and
-- prana-db/migrations/039_audit_role_revoke.sql for the full rationale.
-- Must run after every table above exists.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'prana_app_role') THEN
    CREATE ROLE prana_app_role LOGIN PASSWORD 'prana_app_role';  -- dev-only default
  END IF;
END
$$;

GRANT CONNECT ON DATABASE prana TO prana_app_role;
GRANT USAGE ON SCHEMA public TO prana_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prana_app_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO prana_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prana_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO prana_app_role;

-- The carve-out: audit_event is append-only by policy. INSERT still works
-- (AuditConsumer's dual-write path); UPDATE/DELETE no longer do.
REVOKE UPDATE, DELETE ON audit_event FROM prana_app_role;
