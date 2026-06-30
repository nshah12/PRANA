-- PRANA Dev Seed
-- Loads synthetic data for local development and pipeline testing.
-- NEVER run against staging or production.
-- pan_token = encode(hmac('SYNTHETIC_PAN_{n}', 'dev_secret', 'sha256'), 'hex')
-- Real PANs are NEVER stored here. enc_pan and enc_dek are dev placeholders only.
--
-- Matches sampleData/ zip files:
--   TechCorp    → Employee001–Employee500 (SalarySlips_500emp_3months, etc.)
--   ABCD Bank   → Employee004,013,014,016,017,045,048,050,053,058,072,080,082,102,111,112,113,115,120,126,141,143,173,175,184
--   PQRS Fintech→ Employee195,215,217,230,259,280,288,302,303,309,328,333,347,358,360,367,378,380,389,391,413,415,446,457,491

BEGIN;

-- ============================================================
-- PORTAL ADMIN
-- ============================================================
-- Password: Prana@Admin0124  (Argon2id hash — dev only)
-- TOTP: JBSWY3DPEHPK3PXP dev secret (AES-256-GCM encrypted with 32-zero-byte dev DEK)
-- Use the same "PRANA Dev" authenticator entry as OA users
INSERT INTO portal_admin
  (pa_id, email, password_hash, status, failed_totp_count, totp_secret_enc, totp_configured_at)
VALUES
  ('00000000-0000-0000-0000-000000000001',
   'admin@prana.in',
   '$argon2id$v=19$m=65536,t=2,p=2$v1IK5h0cAV6pMKgZGj+x5Q$zo5H2rqMaLcDmTpLOegF2jzWn365MC5+oVUTFJlB2E4',
   'ACTIVE', 0,
   'S8T6sSddYaqbY0zTcQVdToNL1L6TDQMluxVR6OmP7xuTt0I/9LhXIL8aJiU=',
   NOW());

-- ============================================================
-- TENANTS
-- ============================================================

INSERT INTO tenant (tenant_id, tenant_name, cin, domain, nik_type, kek_arn, primary_state, home_region, status, storage_quota_gb, self_upload_policy) VALUES

  -- TechCorp: large IT company, 500 employees, permissive upload policy
  ('10000000-0000-0000-0000-000000000001',
   'TechCorp Solutions Pvt Ltd',
   'U72900MH2010PTC123456',
   'techcorp.in',
   'PAN',
   'arn:aws:kms:ap-south-1:123456789012:key/dev-techcorp-kek',
   'Maharashtra',
   'ap-south-1',
   'ACTIVE',
   200,
   'ALLOWED_WITH_WARNING'),

  -- ABCD Bank: BFSI, 25 employees, strictest upload policy
  ('10000000-0000-0000-0000-000000000002',
   'ABCD Bank Ltd',
   'L65110MH1994PLC081595',
   'abcdbank.in',
   'PAN',
   'arn:aws:kms:ap-south-1:123456789012:key/dev-abcdbank-kek',
   'Maharashtra',
   'ap-south-1',
   'ACTIVE',
   100,
   'BLOCKED_ENTIRELY'),   -- BFSI constraint: employees cannot self-upload

  -- PQRS Fintech: mid-size fintech, 25 employees
  ('10000000-0000-0000-0000-000000000003',
   'PQRS Fintech Pvt Ltd',
   'U74999KA2018PTC123789',
   'pqrsfintech.in',
   'PAN',
   'arn:aws:kms:ap-south-1:123456789012:key/dev-pqrs-kek',
   'Karnataka',
   'ap-south-2',
   'ACTIVE',
   50,
   'ALLOWED_WITH_WARNING');

-- BFSI tenant config: lock employee_choice OTP channel
INSERT INTO platform_config (config_key, config_value, value_type, description) VALUES
  ('activation_otp_channel', 'corporate_email', 'STRING', 'OTP channel for account activation')
  ON CONFLICT (config_key) DO NOTHING;

INSERT INTO tenant_config (tenant_id, config_key, config_value) VALUES
  ('10000000-0000-0000-0000-000000000002', 'activation_otp_channel', 'corporate_email');

-- ============================================================
-- OA USERS (1 OA-Admin + 1 OA-Operator per tenant)
-- ============================================================
-- All passwords: DevOA@123 (placeholder hash, force_reset=TRUE)

INSERT INTO oa_user (oa_user_id, tenant_id, email, role, temp_password_hash, force_reset, status) VALUES
  -- TechCorp
  ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'admin@techcorp.in',    'oa_admin',    '$argon2id$DEV_HASH', TRUE, 'ACTIVE'),
  ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'operator@techcorp.in', 'oa_operator', '$argon2id$DEV_HASH', TRUE, 'ACTIVE'),
  -- ABCD Bank
  ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', 'admin@abcdbank.in',    'oa_admin',    '$argon2id$DEV_HASH', TRUE, 'ACTIVE'),
  ('20000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', 'operator@abcdbank.in', 'oa_operator', '$argon2id$DEV_HASH', TRUE, 'ACTIVE'),
  -- PQRS Fintech
  ('20000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000003', 'admin@pqrsfintech.in',    'oa_admin',    '$argon2id$DEV_HASH', TRUE, 'ACTIVE'),
  ('20000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000003', 'operator@pqrsfintech.in', 'oa_operator', '$argon2id$DEV_HASH', TRUE, 'ACTIVE');

-- ============================================================
-- EMPLOYEE USERS (pan_token via pgcrypto HMAC — no raw PAN stored)
-- enc_pan and enc_dek are dev placeholders; real values produced by pipeline
-- ============================================================

INSERT INTO employee_user (employee_user_id, pan_token, enc_pan, enc_dek, mobile, status, activated_at)
SELECT
  -- Deterministic UUID from employee number for stable FK references in seeds
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'),   -- placeholder, never real PAN
  'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),   -- placeholder
  '+91900' || LPAD(n::text, 7, '0'),          -- synthetic mobile: +919000000001 … +919000000500
  'ACTIVE',
  NOW() - (random() * 365 * 2 || ' days')::interval
FROM generate_series(1, 500) AS n;

-- ============================================================
-- EMPLOYEE MASTER — TechCorp (all 500 employees)
-- ============================================================

INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, status
)
SELECT
  ('40000000-0000-0000-0001-' || LPAD(n::text, 12, '0'))::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000001',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'),
  'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'TC' || LPAD(n::text, 4, '0'),   -- emp_id_org: TC0001 … TC0500
  'Dev Employee ' || LPAD(n::text, 3, '0'),
  (ARRAY['Software Engineer','Senior Engineer','Tech Lead','Manager','Senior Manager',
         'Director','VP Engineering','Analyst','Senior Analyst','Consultant'])[((n-1) % 10) + 1],
  (ARRAY['Engineering','Product','Finance','HR','Operations','Sales','Marketing',
         'Legal','Design','Data Science'])[((n-1) % 10) + 1],
  (ARRAY['L1','L2','L3','L4','L5','L6'])[((n-1) % 6) + 1],
  (ARRAY['Mumbai','Pune','Bengaluru','Hyderabad','Chennai','Delhi','Noida','Gurugram'])[((n-1) % 8) + 1],
  'PERMANENT',
  (DATE '2020-01-01' + (n * 3 || ' days')::interval)::date,
  'ACTIVE'
FROM generate_series(1, 500) AS n;

-- ============================================================
-- EMPLOYEE MASTER — ABCD Bank (25 employees, subset of 500)
-- These employees have career history at BOTH TechCorp and ABCD Bank
-- ============================================================

INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0000-0002-' || LPAD(n::text, 12, '0'))::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000002',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'),
  'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'ABCD' || LPAD(n::text, 4, '0'),
  'Dev Employee ' || LPAD(n::text, 3, '0'),
  (ARRAY['Branch Manager','Senior Analyst','Credit Officer','Relationship Manager',
         'Operations Head','Risk Analyst','Compliance Officer','IT Manager',
         'Treasury Analyst','HR Manager'])[((n-1) % 10) + 1],
  (ARRAY['Retail Banking','Corporate Banking','Risk','Compliance','Operations',
         'Technology','HR','Treasury','Credit','Branch'])[((n-1) % 10) + 1],
  (ARRAY['A1','A2','B1','B2','C1'])[((n-1) % 5) + 1],
  'Mumbai',
  'PERMANENT',
  DATE '2018-04-01',   -- joined ABCD Bank before TechCorp (earlier employer)
  DATE '2021-03-31',   -- left ABCD Bank (alumni)
  'ALUMNI'
FROM (VALUES (4),(13),(14),(16),(17),(45),(48),(50),(53),(58),
             (72),(80),(82),(102),(111),(112),(113),(115),(120),(126),
             (141),(143),(173),(175),(184)) AS t(n);

-- ============================================================
-- EMPLOYEE MASTER — PQRS Fintech (25 employees, subset of 500)
-- ============================================================

INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, status
)
SELECT
  ('40000000-0000-0000-0003-' || LPAD(n::text, 12, '0'))::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000003',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'),
  'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'PQRS' || LPAD(n::text, 4, '0'),
  'Dev Employee ' || LPAD(n::text, 3, '0'),
  (ARRAY['Product Manager','Backend Engineer','Data Engineer','DevOps Engineer',
         'QA Engineer','ML Engineer','Business Analyst','Scrum Master',
         'Frontend Engineer','Platform Engineer'])[((n-1) % 10) + 1],
  (ARRAY['Product','Engineering','Data','Platform','QA',
         'ML','Business','Agile','Frontend','Infrastructure'])[((n-1) % 10) + 1],
  (ARRAY['IC1','IC2','IC3','M1','M2'])[((n-1) % 5) + 1],
  (ARRAY['Bengaluru','Hyderabad','Pune'])[((n-1) % 3) + 1],
  'PERMANENT',
  DATE '2022-07-01',
  'ACTIVE'
FROM (VALUES (195),(215),(217),(230),(259),(280),(288),(302),(303),(309),
             (328),(333),(347),(358),(360),(367),(378),(380),(389),(391),
             (413),(415),(446),(457),(491)) AS t(n);

-- ============================================================
-- CAREER EVENTS (JOINED events for all tenures)
-- ============================================================

-- TechCorp join events
INSERT INTO career_event (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
SELECT
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  ('40000000-0000-0000-0001-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000001',
  'JOINED',
  (DATE '2020-01-01' + (n * 3 || ' days')::interval)::date,
  'Joined TechCorp Solutions',
  TRUE
FROM generate_series(1, 500) AS n;

-- ABCD Bank join events (alumni)
INSERT INTO career_event (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
SELECT
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  ('40000000-0000-0000-0002-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000002',
  'JOINED',
  DATE '2018-04-01',
  'Joined ABCD Bank',
  TRUE
FROM (VALUES (4),(13),(14),(16),(17),(45),(48),(50),(53),(58),
             (72),(80),(82),(102),(111),(112),(113),(115),(120),(126),
             (141),(143),(173),(175),(184)) AS t(n);

-- ABCD Bank exit events
INSERT INTO career_event (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
SELECT
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  ('40000000-0000-0000-0002-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000002',
  'EXITED',
  DATE '2021-03-31',
  'Resigned from ABCD Bank',
  TRUE
FROM (VALUES (4),(13),(14),(16),(17),(45),(48),(50),(53),(58),
             (72),(80),(82),(102),(111),(112),(113),(115),(120),(126),
             (141),(143),(173),(175),(184)) AS t(n);

-- PQRS Fintech join events
INSERT INTO career_event (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
SELECT
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  ('40000000-0000-0000-0003-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000003',
  'JOINED',
  DATE '2022-07-01',
  'Joined PQRS Fintech',
  TRUE
FROM (VALUES (195),(215),(217),(230),(259),(280),(288),(302),(303),(309),
             (328),(333),(347),(358),(360),(367),(378),(380),(389),(391),
             (413),(415),(446),(457),(491)) AS t(n);

-- ============================================================
-- VAULT HEALTH SCORES (initial zeros — recomputed by pipeline)
-- ============================================================

INSERT INTO vault_health_score (pan_token, overall_score, computed_at)
SELECT
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  0,
  NOW()
FROM generate_series(1, 500) AS n;

COMMIT;

-- ============================================================
-- VERIFICATION QUERIES (run after seeding to sanity-check)
-- ============================================================
-- SELECT COUNT(*) FROM employee_user;                          -- expect 500
-- SELECT COUNT(*) FROM employee_master;                        -- expect 550 (500+25+25)
-- SELECT tenant_name, COUNT(*) FROM employee_master em
--   JOIN tenant t USING (tenant_id) GROUP BY tenant_name;     -- TechCorp:500, ABCD:25, PQRS:25
-- SELECT COUNT(DISTINCT pan_token) FROM employee_master
--   WHERE tenant_id = '10000000-0000-0000-0000-000000000002'
--   AND pan_token IN (SELECT pan_token FROM employee_master
--   WHERE tenant_id = '10000000-0000-0000-0000-000000000001'); -- expect 25 (cross-tenant overlap)
