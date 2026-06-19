-- dev_seed_rich10.sql
-- Rich multi-org career vault for employees 001-010.
-- Run AFTER dev_seed.sql and dev_seed_emp_auth.sql.
-- NEVER run against staging or production.
--
-- Career structure:
--   Emp 001 (Rahul Sharma)   — 1 org : TechCorp only
--   Emp 002 (Priya Nair)     — 2 orgs: Nexus → TechCorp
--   Emp 003 (Amit Patel)     — 3 orgs: Meridian → Nexus → TechCorp
--   Emp 004 (Deepika Reddy)  — 4 orgs: Zephyr → Meridian → Nexus → TechCorp
--   Emp 005 (Kiran Kumar)    — 5 orgs: Pinnacle → Zephyr → Meridian → Nexus → TechCorp
--   Emp 006 (Sneha Joshi)    — 6 orgs: Horizon → Pinnacle → Zephyr → Meridian → Nexus → TechCorp
--   Emp 007 (Rohan Mehta)    — 7 orgs: Aurora → Horizon → Pinnacle → Zephyr → Meridian → Nexus → TechCorp
--   Emp 008 (Ananya Singh)   — 8 orgs: Cascade → Aurora → Horizon → Pinnacle → Zephyr → Meridian → Nexus → TechCorp
--   Emp 009 (Vikram Iyer)    — 9 orgs: ABCD Bank → Cascade → Aurora → Horizon → Pinnacle → Zephyr → Meridian → Nexus → TechCorp
--   Emp 010 (Pooja Sharma)   — 10 orgs: PQRS → ABCD Bank → Cascade → Aurora → Horizon → Pinnacle → Zephyr → Meridian → Nexus → TechCorp

BEGIN;

-- ============================================================
-- TENANTS 4-10 (7 additional employers)
-- ============================================================
INSERT INTO tenant (
  tenant_id, tenant_name, cin, domain, nik_type, kek_arn,
  primary_state, home_region, status, storage_quota_gb, self_upload_policy
) VALUES
  ('10000000-0000-0000-0000-000000000004',
   'Nexus Software Pvt Ltd', 'U72900KA2008PTC123451', 'nexussoftware.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-nexus-kek',
   'Karnataka', 'ap-south-2', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000005',
   'Meridian Capital Ltd', 'U65920MH2005PLC123452', 'meridiancapital.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-meridian-kek',
   'Maharashtra', 'ap-south-1', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000006',
   'Zephyr Analytics Pvt Ltd', 'U74999MH2010PTC123453', 'zephyranalytics.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-zephyr-kek',
   'Maharashtra', 'ap-south-1', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000007',
   'Pinnacle Manufacturing Ltd', 'L28910GJ2002PLC123454', 'pinnacleindia.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-pinnacle-kek',
   'Gujarat', 'ap-south-1', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000008',
   'Horizon Consulting Pvt Ltd', 'U74140DL2000PTC123455', 'horizonconsulting.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-horizon-kek',
   'Delhi', 'ap-south-1', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000009',
   'Aurora Pharma Ltd', 'L24210TG1996PLC123456', 'aurorapharma.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-aurora-kek',
   'Telangana', 'ap-south-2', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000010',
   'Cascade Retail Pvt Ltd', 'U52100TN2003PTC123457', 'cascaderetail.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-cascade-kek',
   'Tamil Nadu', 'ap-south-2', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING');

-- ============================================================
-- CHRO / CFO / CISO for TechCorp (tenant 1)
-- Password: DevEmp@123
-- TOTP: totp_secret_enc=NULL → portal shows QR setup screen on first login.
--       Each user scans their own unique QR and configures their authenticator.
-- ============================================================
INSERT INTO oa_user (
  oa_user_id, tenant_id, email, role,
  password_hash, temp_password_hash, force_reset, status
) VALUES
  ('20000000-0001-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000001', 'chro@techcorp.in', 'chro',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0001-0000-0000-000000000002',
   '10000000-0000-0000-0000-000000000001', 'cfo@techcorp.in', 'cfo',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0001-0000-0000-000000000003',
   '10000000-0000-0000-0000-000000000001', 'ciso@techcorp.in', 'ciso',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE');

-- Patch existing TechCorp OA-Admin and OA-Operator: set real password, clear fake hash.
-- totp_secret_enc stays NULL — each user sets up their own TOTP on first login.
UPDATE oa_user SET
  password_hash      = '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
  temp_password_hash = NULL,
  force_reset        = FALSE
WHERE tenant_id = '10000000-0000-0000-0000-000000000001'
  AND oa_user_id IN (
    '20000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000002'
  );

-- ============================================================
-- OA ADMIN for tenants 4-10 (1 admin each, for Portal access)
-- TOTP: NULL — system generates unique QR per user on first login.
-- ============================================================
INSERT INTO oa_user (
  oa_user_id, tenant_id, email, role,
  password_hash, temp_password_hash, force_reset, status
) VALUES
  ('20000000-0000-0004-0001-000000000001',
   '10000000-0000-0000-0000-000000000004', 'admin@nexussoftware.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0005-0001-000000000001',
   '10000000-0000-0000-0000-000000000005', 'admin@meridiancapital.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0006-0001-000000000001',
   '10000000-0000-0000-0000-000000000006', 'admin@zephyranalytics.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0007-0001-000000000001',
   '10000000-0000-0000-0000-000000000007', 'admin@pinnacleindia.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0008-0001-000000000001',
   '10000000-0000-0000-0000-000000000008', 'admin@horizonconsulting.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0009-0001-000000000001',
   '10000000-0000-0000-0000-000000000009', 'admin@aurorapharma.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE'),

  ('20000000-0000-0010-0001-000000000001',
   '10000000-0000-0000-0000-000000000010', 'admin@cascaderetail.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
   NULL, FALSE, 'ACTIVE');

-- ============================================================
-- UPDATE TechCorp employee_master — give emp001-010 real names
-- ============================================================
UPDATE employee_master SET full_name = 'Rahul Sharma',   designation = 'Software Engineer',      department = 'Engineering',  grade = 'L2' WHERE employee_uuid = '40000000-0000-0000-0001-000000000001';
UPDATE employee_master SET full_name = 'Priya Nair',     designation = 'Data Analyst',            department = 'Data Science', grade = 'L2' WHERE employee_uuid = '40000000-0000-0000-0001-000000000002';
UPDATE employee_master SET full_name = 'Amit Patel',     designation = 'Lead Analyst',            department = 'Analytics',    grade = 'L3' WHERE employee_uuid = '40000000-0000-0000-0001-000000000003';
UPDATE employee_master SET full_name = 'Deepika Reddy',  designation = 'Tech Lead - Analytics',   department = 'Data Science', grade = 'L4' WHERE employee_uuid = '40000000-0000-0000-0001-000000000004';
UPDATE employee_master SET full_name = 'Kiran Kumar',    designation = 'Engineering Manager',      department = 'Engineering',  grade = 'L4' WHERE employee_uuid = '40000000-0000-0000-0001-000000000005';
UPDATE employee_master SET full_name = 'Sneha Joshi',    designation = 'Director of Analytics',   department = 'Analytics',    grade = 'L5' WHERE employee_uuid = '40000000-0000-0000-0001-000000000006';
UPDATE employee_master SET full_name = 'Rohan Mehta',    designation = 'VP Engineering',          department = 'Engineering',  grade = 'L6' WHERE employee_uuid = '40000000-0000-0000-0001-000000000007';
UPDATE employee_master SET full_name = 'Ananya Singh',   designation = 'Chief Product Officer',   department = 'Product',      grade = 'L6' WHERE employee_uuid = '40000000-0000-0000-0001-000000000008';
UPDATE employee_master SET full_name = 'Vikram Iyer',    designation = 'Chief Risk Officer',      department = 'Risk',         grade = 'L6' WHERE employee_uuid = '40000000-0000-0000-0001-000000000009';
UPDATE employee_master SET full_name = 'Pooja Sharma',   designation = 'Chief Executive Officer', department = 'Leadership',   grade = 'L6' WHERE employee_uuid = '40000000-0000-0000-0001-000000000010';

-- Update TechCorp DOJ for emp001-010 (overwrite the generic formula from dev_seed)
UPDATE employee_master SET doj = '2024-01-01' WHERE employee_uuid IN (
  '40000000-0000-0000-0001-000000000001',
  '40000000-0000-0000-0001-000000000002',
  '40000000-0000-0000-0001-000000000003',
  '40000000-0000-0000-0001-000000000004',
  '40000000-0000-0000-0001-000000000005',
  '40000000-0000-0000-0001-000000000006',
  '40000000-0000-0000-0001-000000000007',
  '40000000-0000-0000-0001-000000000008',
  '40000000-0000-0000-0001-000000000009',
  '40000000-0000-0000-0001-000000000010'
);

-- ============================================================
-- EMPLOYEE MASTER — emp009 and emp010 at ABCD Bank (alumni)
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, dol, status
) VALUES
  -- emp009 at ABCD Bank: Credit Risk Analyst, 2000-01-01 → 2002-12-31
  ('40000000-0000-0000-0002-000000000009',
   '30000000-0000-0000-0000-000000000009',
   '10000000-0000-0000-0000-000000000002',
   encode(hmac('SYNTHETIC_PAN_009', 'dev_secret', 'sha256'), 'hex'),
   'DEV_ENC_PAN_009', 'DEV_ENC_DEK_009',
   'ABCD0009', 'Vikram Iyer', 'Credit Risk Analyst', 'Risk',
   'A1', 'Mumbai', 'PERMANENT', '2000-01-01', '2002-12-31', 'ALUMNI'),

  -- emp010 at ABCD Bank: Product Manager - Digital, 2003-01-01 → 2005-12-31
  ('40000000-0000-0000-0002-000000000010',
   '30000000-0000-0000-0000-000000000010',
   '10000000-0000-0000-0000-000000000002',
   encode(hmac('SYNTHETIC_PAN_010', 'dev_secret', 'sha256'), 'hex'),
   'DEV_ENC_PAN_010', 'DEV_ENC_DEK_010',
   'ABCD0010', 'Pooja Sharma', 'Product Manager - Digital', 'Digital Banking',
   'B1', 'Mumbai', 'PERMANENT', '2003-01-01', '2005-12-31', 'ALUMNI');

-- ============================================================
-- EMPLOYEE MASTER — emp010 at PQRS Fintech (alumni)
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, dol, status
) VALUES
  -- emp010 at PQRS Fintech: Junior Product Manager, 2000-01-01 → 2002-12-31
  ('40000000-0000-0000-0003-000000000010',
   '30000000-0000-0000-0000-000000000010',
   '10000000-0000-0000-0000-000000000003',
   encode(hmac('SYNTHETIC_PAN_010', 'dev_secret', 'sha256'), 'hex'),
   'DEV_ENC_PAN_010', 'DEV_ENC_DEK_010',
   'PQRS0010', 'Pooja Sharma', 'Junior Product Manager', 'Product',
   'IC1', 'Bengaluru', 'PERMANENT', '2000-01-01', '2002-12-31', 'ALUMNI');

-- ============================================================
-- EMPLOYEE MASTER — Nexus Software (org 4, emp002-010 alumni)
-- DOJ: 2021-01-01   DOL: 2023-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0004-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000004',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'NX' || LPAD(n::text, 4, '0'),
  (ARRAY['Priya Nair','Amit Patel','Deepika Reddy','Kiran Kumar','Sneha Joshi',
         'Rohan Mehta','Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-1],
  (ARRAY['Junior Data Analyst','Senior Analyst','Senior Data Scientist','Lead Engineer',
         'Senior Manager','Director of Engineering','SVP Product','SVP Risk & Compliance','Co-Founder & CTO'])[n-1],
  (ARRAY['Data','Analytics','Data Science','Engineering','Analytics',
         'Engineering','Product','Risk','Product'])[n-1],
  (ARRAY['L1','L2','L3','L3','L4','L5','L6','L6','L6'])[n-1],
  (ARRAY['Bengaluru','Bengaluru','Bengaluru','Bengaluru',
         'Bengaluru','Bengaluru','Bengaluru','Bengaluru','Bengaluru'])[n-1],
  'PERMANENT', '2021-01-01', '2023-12-31', 'ALUMNI'
FROM generate_series(2, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Meridian Capital (org 5, emp003-010 alumni)
-- DOJ: 2018-01-01   DOL: 2020-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0005-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000005',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'MER' || LPAD(n::text, 4, '0'),
  (ARRAY['Amit Patel','Deepika Reddy','Kiran Kumar','Sneha Joshi',
         'Rohan Mehta','Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-2],
  (ARRAY['Credit Analyst','Data Scientist','Senior Engineer','Lead Analyst',
         'Senior Manager Engineering','VP Product','VP Risk Management','Managing Director'])[n-2],
  (ARRAY['Credit','Analytics','Engineering','Analytics',
         'Engineering','Product','Risk','Strategy'])[n-2],
  (ARRAY['A2','L2','L3','L3','L4','L5','L6','L6'])[n-2],
  'Mumbai', 'PERMANENT', '2018-01-01', '2020-12-31', 'ALUMNI'
FROM generate_series(3, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Zephyr Analytics (org 6, emp004-010 alumni)
-- DOJ: 2015-01-01   DOL: 2017-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0006-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000006',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'ZPH' || LPAD(n::text, 4, '0'),
  (ARRAY['Deepika Reddy','Kiran Kumar','Sneha Joshi','Rohan Mehta',
         'Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-3],
  (ARRAY['Junior Data Scientist','Engineer','Senior Analyst','Engineering Manager',
         'Director - Product','Director - Risk & Analytics','Chief Product Officer'])[n-3],
  (ARRAY['Data Science','Engineering','Analytics','Engineering',
         'Product','Risk','Product'])[n-3],
  (ARRAY['L1','L2','L3','L4','L5','L6','L6'])[n-3],
  'Pune', 'PERMANENT', '2015-01-01', '2017-12-31', 'ALUMNI'
FROM generate_series(4, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Pinnacle Manufacturing (org 7, emp005-010 alumni)
-- DOJ: 2012-01-01   DOL: 2014-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0007-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000007',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'PNK' || LPAD(n::text, 4, '0'),
  (ARRAY['Kiran Kumar','Sneha Joshi','Rohan Mehta','Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-4],
  (ARRAY['Junior Engineer','Business Analyst','Tech Lead','Head of Product','Head of Risk','SVP Product'])[n-4],
  (ARRAY['Engineering','Analytics','Engineering','Product','Risk','Product'])[n-4],
  (ARRAY['L1','L2','L3','L4','L5','L6'])[n-4],
  'Ahmedabad', 'PERMANENT', '2012-01-01', '2014-12-31', 'ALUMNI'
FROM generate_series(5, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Horizon Consulting (org 8, emp006-010 alumni)
-- DOJ: 2009-01-01   DOL: 2011-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0008-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000008',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'HRZ' || LPAD(n::text, 4, '0'),
  (ARRAY['Sneha Joshi','Rohan Mehta','Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-5],
  (ARRAY['Business Analyst','Senior Engineer','Senior Product Manager','Risk Manager','VP Product Strategy'])[n-5],
  (ARRAY['Consulting','Engineering','Product','Risk','Strategy'])[n-5],
  (ARRAY['L1','L2','L3','L3','L4'])[n-5],
  'Delhi', 'PERMANENT', '2009-01-01', '2011-12-31', 'ALUMNI'
FROM generate_series(6, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Aurora Pharma (org 9, emp007-010 alumni)
-- DOJ: 2006-01-01   DOL: 2008-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0009-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000009',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'AUR' || LPAD(n::text, 4, '0'),
  (ARRAY['Rohan Mehta','Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-6],
  (ARRAY['Software Engineer','Product Analyst','Senior Risk Analyst','Product Director'])[n-6],
  (ARRAY['Engineering','Product','Risk','Product'])[n-6],
  (ARRAY['L1','L2','L2','L3'])[n-6],
  'Hyderabad', 'PERMANENT', '2006-01-01', '2008-12-31', 'ALUMNI'
FROM generate_series(7, 10) AS n;

-- ============================================================
-- EMPLOYEE MASTER — Cascade Retail (org 10, emp008-010 alumni)
-- DOJ: 2003-01-01   DOL: 2005-12-31
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek, emp_id_org, full_name,
  designation, department, grade, location, employment_type, doj, dol, status
)
SELECT
  ('40000000-0000-0010-' || LPAD(n::text, 4, '0') || '-000000000001')::uuid,
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  '10000000-0000-0000-0000-000000000010',
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'), 'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  'CSD' || LPAD(n::text, 4, '0'),
  (ARRAY['Ananya Singh','Vikram Iyer','Pooja Sharma'])[n-7],
  (ARRAY['Retail Analyst','Senior Analyst','Senior Product Manager'])[n-7],
  (ARRAY['Retail Operations','Risk','Product'])[n-7],
  (ARRAY['L1','L2','L3'])[n-7],
  'Chennai', 'PERMANENT', '2003-01-01', '2005-12-31', 'ALUMNI'
FROM generate_series(8, 10) AS n;

-- ============================================================
-- AUTH CREDENTIALS for emp003-010 (Password: DevEmp@123)
-- ============================================================
-- Employees use SMS OTP for login — no TOTP pre-configuration needed.
-- totp_secret_enc stays NULL; employees set up 2FA in-app if they choose to.
UPDATE employee_user
SET
  password_hash  = '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
  consent_status = 'GRANTED',
  force_reset    = FALSE,
  status         = 'ACTIVE',
  email          = 'emp' || LPAD(n::text, 3, '0') || '@test.prana'
FROM generate_series(3, 10) AS n
WHERE employee_user_id = ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid;

-- ============================================================
-- DOCUMENTS — build via temp staging table for reusability
-- ============================================================

CREATE TEMP TABLE _stints (
  emp_n        INT,
  emp_name     TEXT,
  emp_user_id  UUID,
  emp_uuid     UUID,
  tenant_id    UUID,
  employer     TEXT,
  designation  TEXT,
  doj          DATE,
  dol          DATE,       -- NULL = current employer
  is_alumni    BOOLEAN
);

INSERT INTO _stints VALUES
  -- ── Emp 001 Rahul Sharma ─────────────────────────────────────────────
  (1,'Rahul Sharma','30000000-0000-0000-0000-000000000001','40000000-0000-0000-0001-000000000001','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Software Engineer','2024-01-01',NULL,FALSE),
  -- ── Emp 002 Priya Nair ───────────────────────────────────────────────
  (2,'Priya Nair','30000000-0000-0000-0000-000000000002','40000000-0000-0004-0002-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Junior Data Analyst','2021-01-01','2023-12-31',TRUE),
  (2,'Priya Nair','30000000-0000-0000-0000-000000000002','40000000-0000-0000-0001-000000000002','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Data Analyst','2024-01-01',NULL,FALSE),
  -- ── Emp 003 Amit Patel ───────────────────────────────────────────────
  (3,'Amit Patel','30000000-0000-0000-0000-000000000003','40000000-0000-0005-0003-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Credit Analyst','2018-01-01','2020-12-31',TRUE),
  (3,'Amit Patel','30000000-0000-0000-0000-000000000003','40000000-0000-0004-0003-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Senior Analyst','2021-01-01','2023-12-31',TRUE),
  (3,'Amit Patel','30000000-0000-0000-0000-000000000003','40000000-0000-0000-0001-000000000003','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Lead Analyst','2024-01-01',NULL,FALSE),
  -- ── Emp 004 Deepika Reddy ────────────────────────────────────────────
  (4,'Deepika Reddy','30000000-0000-0000-0000-000000000004','40000000-0000-0006-0004-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Junior Data Scientist','2015-01-01','2017-12-31',TRUE),
  (4,'Deepika Reddy','30000000-0000-0000-0000-000000000004','40000000-0000-0005-0004-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Data Scientist','2018-01-01','2020-12-31',TRUE),
  (4,'Deepika Reddy','30000000-0000-0000-0000-000000000004','40000000-0000-0004-0004-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Senior Data Scientist','2021-01-01','2023-12-31',TRUE),
  (4,'Deepika Reddy','30000000-0000-0000-0000-000000000004','40000000-0000-0000-0001-000000000004','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Tech Lead - Analytics','2024-01-01',NULL,FALSE),
  -- ── Emp 005 Kiran Kumar ──────────────────────────────────────────────
  (5,'Kiran Kumar','30000000-0000-0000-0000-000000000005','40000000-0000-0007-0005-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','Junior Engineer','2012-01-01','2014-12-31',TRUE),
  (5,'Kiran Kumar','30000000-0000-0000-0000-000000000005','40000000-0000-0006-0005-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Engineer','2015-01-01','2017-12-31',TRUE),
  (5,'Kiran Kumar','30000000-0000-0000-0000-000000000005','40000000-0000-0005-0005-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Senior Engineer','2018-01-01','2020-12-31',TRUE),
  (5,'Kiran Kumar','30000000-0000-0000-0000-000000000005','40000000-0000-0004-0005-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Lead Engineer','2021-01-01','2023-12-31',TRUE),
  (5,'Kiran Kumar','30000000-0000-0000-0000-000000000005','40000000-0000-0000-0001-000000000005','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Engineering Manager','2024-01-01',NULL,FALSE),
  -- ── Emp 006 Sneha Joshi ──────────────────────────────────────────────
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0008-0006-000000000001','10000000-0000-0000-0000-000000000008','Horizon Consulting Pvt Ltd','Business Analyst','2009-01-01','2011-12-31',TRUE),
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0007-0006-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','Senior Analyst','2012-01-01','2014-12-31',TRUE),
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0006-0006-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Lead Analyst','2015-01-01','2017-12-31',TRUE),
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0005-0006-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Analytics Manager','2018-01-01','2020-12-31',TRUE),
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0004-0006-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Senior Manager','2021-01-01','2023-12-31',TRUE),
  (6,'Sneha Joshi','30000000-0000-0000-0000-000000000006','40000000-0000-0000-0001-000000000006','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Director of Analytics','2024-01-01',NULL,FALSE),
  -- ── Emp 007 Rohan Mehta ──────────────────────────────────────────────
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0009-0007-000000000001','10000000-0000-0000-0000-000000000009','Aurora Pharma Ltd','Software Engineer','2006-01-01','2008-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0008-0007-000000000001','10000000-0000-0000-0000-000000000008','Horizon Consulting Pvt Ltd','Senior Engineer','2009-01-01','2011-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0007-0007-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','Tech Lead','2012-01-01','2014-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0006-0007-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Engineering Manager','2015-01-01','2017-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0005-0007-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Senior Manager Engineering','2018-01-01','2020-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0004-0007-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Director of Engineering','2021-01-01','2023-12-31',TRUE),
  (7,'Rohan Mehta','30000000-0000-0000-0000-000000000007','40000000-0000-0000-0001-000000000007','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','VP Engineering','2024-01-01',NULL,FALSE),
  -- ── Emp 008 Ananya Singh ─────────────────────────────────────────────
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0010-0008-000000000001','10000000-0000-0000-0000-000000000010','Cascade Retail Pvt Ltd','Retail Analyst','2003-01-01','2005-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0009-0008-000000000001','10000000-0000-0000-0000-000000000009','Aurora Pharma Ltd','Product Analyst','2006-01-01','2008-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0008-0008-000000000001','10000000-0000-0000-0000-000000000008','Horizon Consulting Pvt Ltd','Senior Product Manager','2009-01-01','2011-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0007-0008-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','Head of Product','2012-01-01','2014-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0006-0008-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Director of Product','2015-01-01','2017-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0005-0008-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','VP Product','2018-01-01','2020-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0004-0008-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','SVP Product','2021-01-01','2023-12-31',TRUE),
  (8,'Ananya Singh','30000000-0000-0000-0000-000000000008','40000000-0000-0000-0001-000000000008','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Chief Product Officer','2024-01-01',NULL,FALSE),
  -- ── Emp 009 Vikram Iyer ──────────────────────────────────────────────
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0000-0002-000000000009','10000000-0000-0000-0000-000000000002','ABCD Bank Ltd','Credit Risk Analyst','2000-01-01','2002-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0010-0009-000000000001','10000000-0000-0000-0000-000000000010','Cascade Retail Pvt Ltd','Senior Risk Analyst','2003-01-01','2005-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0009-0009-000000000001','10000000-0000-0000-0000-000000000009','Aurora Pharma Ltd','Risk Manager','2006-01-01','2008-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0008-0009-000000000001','10000000-0000-0000-0000-000000000008','Horizon Consulting Pvt Ltd','Senior Manager Risk','2009-01-01','2011-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0007-0009-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','Head of Risk','2012-01-01','2014-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0006-0009-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Director - Risk & Analytics','2015-01-01','2017-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0005-0009-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','VP Risk Management','2018-01-01','2020-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0004-0009-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','SVP Risk & Compliance','2021-01-01','2023-12-31',TRUE),
  (9,'Vikram Iyer','30000000-0000-0000-0000-000000000009','40000000-0000-0000-0001-000000000009','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Chief Risk Officer','2024-01-01',NULL,FALSE),
  -- ── Emp 010 Pooja Sharma ─────────────────────────────────────────────
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0000-0003-000000000010','10000000-0000-0000-0000-000000000003','PQRS Fintech Pvt Ltd','Junior Product Manager','2000-01-01','2002-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0000-0002-000000000010','10000000-0000-0000-0000-000000000002','ABCD Bank Ltd','Product Manager - Digital','2003-01-01','2005-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0010-0010-000000000001','10000000-0000-0000-0000-000000000010','Cascade Retail Pvt Ltd','Senior Product Manager','2006-01-01','2008-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0009-0010-000000000001','10000000-0000-0000-0000-000000000009','Aurora Pharma Ltd','Product Director','2009-01-01','2011-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0008-0010-000000000001','10000000-0000-0000-0000-000000000008','Horizon Consulting Pvt Ltd','VP Product Strategy','2012-01-01','2014-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0007-0010-000000000001','10000000-0000-0000-0000-000000000007','Pinnacle Manufacturing Ltd','SVP Product','2015-01-01','2017-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0006-0010-000000000001','10000000-0000-0000-0000-000000000006','Zephyr Analytics Pvt Ltd','Chief Product Officer','2018-01-01','2020-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0005-0010-000000000001','10000000-0000-0000-0000-000000000005','Meridian Capital Ltd','Managing Director','2021-01-01','2023-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0004-0010-000000000001','10000000-0000-0000-0000-000000000004','Nexus Software Pvt Ltd','Co-Founder & CTO','2021-01-01','2023-12-31',TRUE),
  (10,'Pooja Sharma','30000000-0000-0000-0000-000000000010','40000000-0000-0000-0001-000000000010','10000000-0000-0000-0000-000000000001','TechCorp Solutions Pvt Ltd','Chief Executive Officer','2024-01-01',NULL,FALSE);

-- Helper to compute pan_token for each emp_n
CREATE TEMP TABLE _pan AS
  SELECT n, encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex') AS pan_token
  FROM generate_series(1, 10) AS n;

-- ── OFFER LETTERS (one per stint) ────────────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('OFFER-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'OFFER_LETTER',
  (s.doj - INTERVAL '30 days')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/OFFER_LETTER/' || (s.doj - INTERVAL '30 days')::date::text || '.pdf',
  'prana-documents-dev',
  (128 + (s.emp_n * 7) % 200) * 1024,
  md5('sha256-offer-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name', jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'designation',   jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'date_of_joining', jsonb_build_object('value', s.doj::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj - INTERVAL '30 days')::timestamptz,
  (s.doj - INTERVAL '28 days')::timestamptz,
  'Offer_Letter.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n;

-- ── JOINING / APPOINTMENT LETTERS ────────────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('JOIN-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'JOINING_LETTER',
  s.doj::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/JOINING_LETTER/' || s.doj::text || '.pdf',
  'prana-documents-dev',
  (96 + (s.emp_n * 11) % 150) * 1024,
  md5('sha256-join-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',  jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name',  jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'designation',    jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'date_of_joining',jsonb_build_object('value', s.doj::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  s.doj::timestamptz,
  (s.doj + INTERVAL '2 days')::timestamptz,
  'Joining_Letter.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n;

-- ── SALARY SLIPS (3 per stint: months 6, 18, 30 of each tenure; capped at dol or today) ───
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('SLIP-' || s.emp_n::text || '-' || s.tenant_id::text || '-' || slip_month.n::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'SALARY_SLIP',
  to_char(s.doj + ((slip_month.n * 6) || ' months')::interval, 'YYYY-MM'),
  s.tenant_id::text || '/' || s.emp_uuid::text || '/SALARY_SLIP/' ||
    to_char(s.doj + ((slip_month.n * 6) || ' months')::interval, 'YYYY-MM') || '.pdf',
  'prana-documents-dev',
  (64 + (s.emp_n * slip_month.n * 13) % 128) * 1024,
  md5('sha256-slip-' || s.emp_n::text || '-' || s.tenant_id::text || '-' || slip_month.n::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name', jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'designation',   jsonb_build_object('value', s.designation, 'confidence', 0.96),
    'department',    jsonb_build_object('value', 'Engineering', 'confidence', 0.94),
    'pay_period',    jsonb_build_object('value', to_char(s.doj + ((slip_month.n * 6) || ' months')::interval, 'Month YYYY'), 'confidence', 0.99),
    'pf_deducted',   jsonb_build_object('value', 'Yes', 'confidence', 0.95),
    'tds_deducted',  jsonb_build_object('value', 'Yes', 'confidence', 0.93)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + ((slip_month.n * 6) || ' months')::interval)::timestamptz,
  (s.doj + ((slip_month.n * 6) || ' months')::interval + INTERVAL '3 days')::timestamptz,
  'Salary_Slip_' || to_char(s.doj + ((slip_month.n * 6) || ' months')::interval, 'Mon_YYYY') || '.pdf'
FROM _stints s
JOIN _pan p ON p.n = s.emp_n
CROSS JOIN (VALUES (1),(2),(3)) AS slip_month(n)
WHERE (s.doj + ((slip_month.n * 6) || ' months')::interval)::date
        <= COALESCE(s.dol, CURRENT_DATE);

-- ── FORM 16 (one per stint, for FY ending within the tenure) ─────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('F16-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'FORM_16',
  'FY:' || (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text
         || '-' || EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/FORM_16/FY_' ||
    (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text || '.pdf',
  'prana-documents-dev',
  (200 + (s.emp_n * 17) % 300) * 1024,
  md5('sha256-f16-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name, 'confidence', 0.99),
    'employer_name', jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'financial_year',jsonb_build_object('value',
      (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text || '-' ||
      EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int::text, 'confidence', 0.99),
    'tds_deducted',  jsonb_build_object('value', 'Yes', 'confidence', 0.97)
  ),
  'ROUTED', FALSE, FALSE,
  (DATE_TRUNC('year', s.doj + INTERVAL '1 year') + INTERVAL '3 months')::timestamptz,
  (DATE_TRUNC('year', s.doj + INTERVAL '1 year') + INTERVAL '3 months 3 days')::timestamptz,
  'Form16.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── PF ACKNOWLEDGEMENT (one per stint) ───────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('PF-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'PF_ACKNOWLEDGEMENT',
  s.doj::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/PF_ACKNOWLEDGEMENT/' || s.doj::text || '.pdf',
  'prana-documents-dev',
  (48 + (s.emp_n * 5) % 80) * 1024,
  md5('sha256-pf-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name', jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'uan_number',    jsonb_build_object('value', '10' || LPAD((s.emp_n * 100000 + 123456)::text, 10, '0'), 'confidence', 0.96),
    'effective_date',jsonb_build_object('value', s.doj::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '30 days')::timestamptz,
  (s.doj + INTERVAL '32 days')::timestamptz,
  'PF_Acknowledgement.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n;

-- ── INCREMENT LETTERS (stints > 12 months) ───────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('INC-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'INCREMENT_LETTER',
  (s.doj + INTERVAL '12 months')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/INCREMENT_LETTER/' ||
    (s.doj + INTERVAL '12 months')::date::text || '.pdf',
  'prana-documents-dev',
  (80 + (s.emp_n * 9) % 120) * 1024,
  md5('sha256-inc-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',  jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name',  jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'designation',    jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'effective_date', jsonb_build_object('value', (s.doj + INTERVAL '12 months')::date::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '12 months')::timestamptz,
  (s.doj + INTERVAL '12 months 3 days')::timestamptz,
  'Increment_Letter.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── PROMOTION LETTERS (stints > 24 months, emp 5 and above) ─────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('PROMO-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'PROMOTION_LETTER',
  (s.doj + INTERVAL '24 months')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/PROMOTION_LETTER/' ||
    (s.doj + INTERVAL '24 months')::date::text || '.pdf',
  'prana-documents-dev',
  (90 + (s.emp_n * 13) % 110) * 1024,
  md5('sha256-promo-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',    jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name',    jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'new_designation',  jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'effective_date',   jsonb_build_object('value', (s.doj + INTERVAL '24 months')::date::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '24 months')::timestamptz,
  (s.doj + INTERVAL '24 months 3 days')::timestamptz,
  'Promotion_Letter.pdf'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE s.emp_n >= 5
  AND (s.doj + INTERVAL '24 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── RELIEVING + EXPERIENCE LETTERS (alumni stints only) ──────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5(letter_type || '-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  letter_type,
  s.dol::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/' || letter_type || '/' || s.dol::text || '.pdf',
  'prana-documents-dev',
  (70 + (s.emp_n * 7) % 100) * 1024,
  md5('sha256-' || letter_type || '-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE,
  'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',    jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name',    jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'designation',      jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'last_working_day', jsonb_build_object('value', s.dol::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  s.dol::timestamptz,
  (s.dol + INTERVAL '3 days')::timestamptz,
  letter_type || '.pdf'
FROM _stints s
JOIN _pan p ON p.n = s.emp_n
CROSS JOIN (VALUES ('RELIEVING_LETTER'), ('EXPERIENCE_LETTER')) AS lt(letter_type)
WHERE s.is_alumni = TRUE;

-- ============================================================
-- CAREER EVENTS
-- ============================================================

-- JOINED events for all stints
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token,
  s.emp_user_id,
  s.emp_uuid,
  s.tenant_id,
  'JOINED',
  s.doj,
  'Joined ' || s.employer || ' as ' || s.designation,
  s.designation,
  CASE
    WHEN s.emp_n <= 2 THEN 'L1'
    WHEN s.emp_n <= 4 THEN 'L2'
    WHEN s.emp_n <= 6 THEN 'L3'
    WHEN s.emp_n <= 8 THEN 'L4'
    ELSE 'L5'
  END,
  TRUE,
  'Career milestone: joined ' || s.employer || ' marking continued professional growth.'
FROM _stints s JOIN _pan p ON p.n = s.emp_n;

-- EXITED events for alumni stints
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token,
  s.emp_user_id,
  s.emp_uuid,
  s.tenant_id,
  'EXITED',
  s.dol,
  'Left ' || s.employer,
  s.designation,
  NULL,
  TRUE,
  'Concluded tenure at ' || s.employer || ' after ' ||
    (s.dol - s.doj) / 365 || ' year(s). Strong exit record maintained.'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE s.is_alumni = TRUE;

-- INCREMENT events (stints > 12 months)
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token,
  s.emp_user_id,
  s.emp_uuid,
  s.tenant_id,
  'INCREMENT',
  (s.doj + INTERVAL '12 months')::date,
  'Annual increment at ' || s.employer,
  s.designation,
  NULL,
  TRUE,
  'Performance-linked increment received at ' || s.employer || '. Progression aligned with market benchmark.'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- PROMOTED events (emp 5+, stints > 24 months)
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token,
  s.emp_user_id,
  s.emp_uuid,
  s.tenant_id,
  'PROMOTED',
  (s.doj + INTERVAL '24 months')::date,
  'Promoted to ' || s.designation || ' at ' || s.employer,
  s.designation,
  NULL,
  TRUE,
  'Promotion to ' || s.designation || ' reflects consistent high performance and leadership growth.'
FROM _stints s JOIN _pan p ON p.n = s.emp_n
WHERE s.emp_n >= 5
  AND (s.doj + INTERVAL '24 months')::date <= COALESCE(s.dol, CURRENT_DATE);

COMMIT;
