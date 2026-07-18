-- dev_seed_3tenant10.sql
-- 10 new employees (emp501-510), each spanning exactly 3 tenants.
-- 3 new tenants: Vertex Technologies (T11), Indigo Capital (T12), Bluestar Pharma (T13).
-- Full OA staff per tenant: OA-Admin, OA-Operator, CHRO, CFO, CISO (15 users total).
-- ~310 documents seeded across all 30 stints.
-- Run AFTER dev_seed.sql (any order relative to dev_seed_emp_auth.sql / dev_seed_rich10.sql).
-- Employee range is 501-510 -- deliberately outside dev_seed.sql's own 1-500 range
-- (dev_seed.sql bulk-creates employee_user rows 1-500; this file used to reuse 11-20,
-- which collided with those already-claimed rows -- see CREDENTIALS.md history note).
-- NEVER run against staging or production.
--
-- Career rotation (each employee spans all 3 tenants):
--   Group A (emp501-504): Vertex(2016-19) → Indigo(2020-22) → Bluestar(2023-cur)
--   Group B (emp505-507): Indigo(2016-19) → Bluestar(2020-22) → Vertex(2023-cur)
--   Group C (emp508-510): Bluestar(2016-19) → Vertex(2020-22) → Indigo(2023-cur)
--
-- Doc count per stint: Offer+Join+3×Salary+F16+PF+Increment+Promotion = 9 (current)
--   Alumni stints add: Relieving+Experience = 11 each
--   Per employee: 11+11+9 = 31 docs  |  10 employees = ~310 docs total

BEGIN;

-- ============================================================
-- 3 NEW TENANTS
-- ============================================================
INSERT INTO tenant (
  tenant_id, tenant_name, cin, domain, nik_type, kek_arn,
  primary_state, home_region, status, storage_quota_gb, self_upload_policy
) VALUES
  ('10000000-0000-0000-0000-000000000011',
   'Vertex Technologies Pvt Ltd', 'U72900MH2012PTC234501', 'vertex.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-vertex-kek',
   'Maharashtra', 'ap-south-1', 'ACTIVE', 100, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000012',
   'Indigo Capital Ltd', 'U65100MH2010PLC234502', 'indigocapital.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-indigo-kek',
   'Maharashtra', 'ap-south-1', 'ACTIVE', 100, 'ALLOWED_WITH_WARNING'),

  ('10000000-0000-0000-0000-000000000013',
   'Bluestar Pharma Pvt Ltd', 'L24230MH2008PLC234503', 'bluestarpharma.in',
   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-bluestar-kek',
   'Telangana', 'ap-south-2', 'ACTIVE', 100, 'ALLOWED_WITH_WARNING');

-- ============================================================
-- OA USERS — 5 roles × 3 tenants = 15 users
-- Password: Prana@Admin0124  |  totp_secret_enc = NULL (QR setup on first login)
-- ============================================================
INSERT INTO oa_user (
  oa_user_id, tenant_id, email, role,
  password_hash, temp_password_hash, force_reset, status
) VALUES
  -- ── Vertex Technologies ──────────────────────────────────────────────────
  ('20000000-0000-0011-0001-000000000001', '10000000-0000-0000-0000-000000000011',
   'admin@vertex.in',    'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0011-0002-000000000001', '10000000-0000-0000-0000-000000000011',
   'ops@vertex.in',      'oa_operator',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0011-0003-000000000001', '10000000-0000-0000-0000-000000000011',
   'chro@vertex.in',     'chro',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0011-0004-000000000001', '10000000-0000-0000-0000-000000000011',
   'cfo@vertex.in',      'cfo',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0011-0005-000000000001', '10000000-0000-0000-0000-000000000011',
   'ciso@vertex.in',     'ciso',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),

  -- ── Indigo Capital ───────────────────────────────────────────────────────
  ('20000000-0000-0012-0001-000000000001', '10000000-0000-0000-0000-000000000012',
   'admin@indigocapital.in',  'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0012-0002-000000000001', '10000000-0000-0000-0000-000000000012',
   'ops@indigocapital.in',    'oa_operator',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0012-0003-000000000001', '10000000-0000-0000-0000-000000000012',
   'chro@indigocapital.in',   'chro',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0012-0004-000000000001', '10000000-0000-0000-0000-000000000012',
   'cfo@indigocapital.in',    'cfo',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0012-0005-000000000001', '10000000-0000-0000-0000-000000000012',
   'ciso@indigocapital.in',   'ciso',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),

  -- ── Bluestar Pharma ──────────────────────────────────────────────────────
  ('20000000-0000-0013-0001-000000000001', '10000000-0000-0000-0000-000000000013',
   'admin@bluestarpharma.in', 'oa_admin',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0013-0002-000000000001', '10000000-0000-0000-0000-000000000013',
   'ops@bluestarpharma.in',   'oa_operator',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0013-0003-000000000001', '10000000-0000-0000-0000-000000000013',
   'chro@bluestarpharma.in',  'chro',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0013-0004-000000000001', '10000000-0000-0000-0000-000000000013',
   'cfo@bluestarpharma.in',   'cfo',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE'),
  ('20000000-0000-0013-0005-000000000001', '10000000-0000-0000-0000-000000000013',
   'ciso@bluestarpharma.in',  'ciso',
   '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
   NULL, FALSE, 'ACTIVE');

-- ============================================================
-- EMPLOYEE USERS (emp501-510)
-- mobile: +919000000{n}   email: emp{n}@test.prana   pwd: Prana@Admin0124
-- OTP: 123456 (dev bypass)
-- ============================================================
INSERT INTO employee_user (
  employee_user_id, pan_token, enc_pan, enc_dek,
  mobile, email, password_hash,
  consent_status, status, force_reset
)
SELECT
  ('30000000-0000-0000-0000-' || LPAD(n::text, 12, '0'))::uuid,
  encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex'),
  'DEV_ENC_PAN_' || LPAD(n::text, 3, '0'),
  'DEV_ENC_DEK_' || LPAD(n::text, 3, '0'),
  '+91900000' || LPAD(n::text, 4, '0'),
  'emp' || LPAD(n::text, 3, '0') || '@test.prana',
  '$argon2id$v=19$m=65536,t=2,p=2$s/wcmu2iiTnuggfacxGIbQ$srpd2ll08Cj3dFCzCZuK6fHX7kLeetqwVMKq1nssDTo',
  'GRANTED', 'ACTIVE', FALSE
FROM generate_series(501, 510) AS n;

-- ============================================================
-- EMPLOYEE MASTER -- 30 rows (10 employees x 3 stints each)
-- UUID scheme: 50000000-00{emp}-00{tenant}-0000-000000000001
-- Group A (011-014): T11(old) → T12(mid) → T13(cur)
-- Group B (015-017): T12(old) → T13(mid) → T11(cur)
-- Group C (018-020): T13(old) → T11(mid) → T12(cur)
-- ============================================================
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id,
  pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department,
  grade, location, employment_type, doj, dol, status
) VALUES

  -- ── Emp 501 Arjun Kapoor ────────────────────────────────────────────────
  ('50000000-0501-0011-0000-000000000001','30000000-0000-0000-0000-000000000501','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_501','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_501','DEV_ENC_DEK_501',
   'VTX0011','Arjun Kapoor','Software Engineer','Engineering',
   'L1','Mumbai','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0501-0012-0000-000000000001','30000000-0000-0000-0000-000000000501','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_501','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_501','DEV_ENC_DEK_501',
   'IDC0011','Arjun Kapoor','Senior Financial Analyst','Finance',
   'A2','Mumbai','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0501-0013-0000-000000000001','30000000-0000-0000-0000-000000000501','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_501','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_501','DEV_ENC_DEK_501',
   'BSP0011','Arjun Kapoor','Research Lead','R&D',
   'M2','Hyderabad','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 502 Meera Krishnan ──────────────────────────────────────────────
  ('50000000-0502-0011-0000-000000000001','30000000-0000-0000-0000-000000000502','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_502','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_502','DEV_ENC_DEK_502',
   'VTX0012','Meera Krishnan','Data Engineer','Data Engineering',
   'L1','Bengaluru','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0502-0012-0000-000000000001','30000000-0000-0000-0000-000000000502','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_502','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_502','DEV_ENC_DEK_502',
   'IDC0012','Meera Krishnan','Senior Risk Analyst','Risk',
   'A2','Mumbai','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0502-0013-0000-000000000001','30000000-0000-0000-0000-000000000502','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_502','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_502','DEV_ENC_DEK_502',
   'BSP0012','Meera Krishnan','Clinical Data Lead','Clinical Operations',
   'M2','Hyderabad','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 503 Siddharth Rao ──────────────────────────────────────────────
  ('50000000-0503-0011-0000-000000000001','30000000-0000-0000-0000-000000000503','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_503','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_503','DEV_ENC_DEK_503',
   'VTX0013','Siddharth Rao','DevOps Engineer','Infrastructure',
   'L2','Pune','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0503-0012-0000-000000000001','30000000-0000-0000-0000-000000000503','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_503','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_503','DEV_ENC_DEK_503',
   'IDC0013','Siddharth Rao','Compliance Analyst','Compliance',
   'A2','Mumbai','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0503-0013-0000-000000000001','30000000-0000-0000-0000-000000000503','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_503','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_503','DEV_ENC_DEK_503',
   'BSP0013','Siddharth Rao','Regulatory Affairs Manager','Regulatory',
   'M3','Hyderabad','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 504 Natasha Verma ──────────────────────────────────────────────
  ('50000000-0504-0011-0000-000000000001','30000000-0000-0000-0000-000000000504','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_504','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_504','DEV_ENC_DEK_504',
   'VTX0014','Natasha Verma','Product Analyst','Product',
   'L2','Bengaluru','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0504-0012-0000-000000000001','30000000-0000-0000-0000-000000000504','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_504','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_504','DEV_ENC_DEK_504',
   'IDC0014','Natasha Verma','Investment Analyst','Investment Banking',
   'A2','Mumbai','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0504-0013-0000-000000000001','30000000-0000-0000-0000-000000000504','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_504','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_504','DEV_ENC_DEK_504',
   'BSP0014','Natasha Verma','QA Lead','Quality Assurance',
   'M2','Hyderabad','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 505 Rajesh Pillai ──────────────────────────────────────────────
  ('50000000-0505-0012-0000-000000000001','30000000-0000-0000-0000-000000000505','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_505','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_505','DEV_ENC_DEK_505',
   'IDC0015','Rajesh Pillai','Financial Analyst','Finance',
   'A1','Chennai','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0505-0013-0000-000000000001','30000000-0000-0000-0000-000000000505','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_505','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_505','DEV_ENC_DEK_505',
   'BSP0015','Rajesh Pillai','Senior Research Scientist','R&D',
   'M2','Hyderabad','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0505-0011-0000-000000000001','30000000-0000-0000-0000-000000000505','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_505','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_505','DEV_ENC_DEK_505',
   'VTX0015','Rajesh Pillai','Senior Software Engineer','Engineering',
   'L3','Bengaluru','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 506 Divya Menon ────────────────────────────────────────────────
  ('50000000-0506-0012-0000-000000000001','30000000-0000-0000-0000-000000000506','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_506','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_506','DEV_ENC_DEK_506',
   'IDC0016','Divya Menon','Risk Analyst','Risk',
   'A1','Kochi','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0506-0013-0000-000000000001','30000000-0000-0000-0000-000000000506','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_506','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_506','DEV_ENC_DEK_506',
   'BSP0016','Divya Menon','Clinical Data Analyst','Clinical Operations',
   'M1','Hyderabad','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0506-0011-0000-000000000001','30000000-0000-0000-0000-000000000506','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_506','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_506','DEV_ENC_DEK_506',
   'VTX0016','Divya Menon','Senior Data Engineer','Data Engineering',
   'L3','Bengaluru','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 507 Aditya Gupta ──────────────────────────────────────────────
  ('50000000-0507-0012-0000-000000000001','30000000-0000-0000-0000-000000000507','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_507','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_507','DEV_ENC_DEK_507',
   'IDC0017','Aditya Gupta','Compliance Analyst','Compliance',
   'A2','Delhi','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0507-0013-0000-000000000001','30000000-0000-0000-0000-000000000507','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_507','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_507','DEV_ENC_DEK_507',
   'BSP0017','Aditya Gupta','Regulatory Affairs Associate','Regulatory',
   'M1','Hyderabad','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0507-0011-0000-000000000001','30000000-0000-0000-0000-000000000507','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_507','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_507','DEV_ENC_DEK_507',
   'VTX0017','Aditya Gupta','Staff Engineer','Platform Engineering',
   'L4','Bengaluru','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 508 Preethi Nambiar ───────────────────────────────────────────
  ('50000000-0508-0013-0000-000000000001','30000000-0000-0000-0000-000000000508','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_508','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_508','DEV_ENC_DEK_508',
   'BSP0018','Preethi Nambiar','Research Associate','R&D',
   'M1','Bengaluru','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0508-0011-0000-000000000001','30000000-0000-0000-0000-000000000508','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_508','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_508','DEV_ENC_DEK_508',
   'VTX0018','Preethi Nambiar','Senior Software Engineer','Engineering',
   'L3','Bengaluru','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0508-0012-0000-000000000001','30000000-0000-0000-0000-000000000508','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_508','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_508','DEV_ENC_DEK_508',
   'IDC0018','Preethi Nambiar','Finance Manager','Finance',
   'B1','Mumbai','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 509 Suresh Babu ───────────────────────────────────────────────
  ('50000000-0509-0013-0000-000000000001','30000000-0000-0000-0000-000000000509','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_509','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_509','DEV_ENC_DEK_509',
   'BSP0019','Suresh Babu','Clinical Data Analyst','Clinical Operations',
   'M1','Chennai','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0509-0011-0000-000000000001','30000000-0000-0000-0000-000000000509','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_509','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_509','DEV_ENC_DEK_509',
   'VTX0019','Suresh Babu','Senior Data Engineer','Data Engineering',
   'L3','Bengaluru','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0509-0012-0000-000000000001','30000000-0000-0000-0000-000000000509','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_509','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_509','DEV_ENC_DEK_509',
   'IDC0019','Suresh Babu','Risk Manager','Risk',
   'B1','Mumbai','PERMANENT','2023-01-01',NULL,'ACTIVE'),

  -- ── Emp 510 Kavya Reddy ───────────────────────────────────────────────
  ('50000000-0510-0013-0000-000000000001','30000000-0000-0000-0000-000000000510','10000000-0000-0000-0000-000000000013',
   encode(hmac('SYNTHETIC_PAN_510','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_510','DEV_ENC_DEK_510',
   'BSP0020','Kavya Reddy','Regulatory Affairs Associate','Regulatory',
   'M2','Hyderabad','PERMANENT','2016-01-01','2019-12-31','ALUMNI'),
  ('50000000-0510-0011-0000-000000000001','30000000-0000-0000-0000-000000000510','10000000-0000-0000-0000-000000000011',
   encode(hmac('SYNTHETIC_PAN_510','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_510','DEV_ENC_DEK_510',
   'VTX0020','Kavya Reddy','Lead Engineer','Engineering',
   'L4','Bengaluru','PERMANENT','2020-01-01','2022-12-31','ALUMNI'),
  ('50000000-0510-0012-0000-000000000001','30000000-0000-0000-0000-000000000510','10000000-0000-0000-0000-000000000012',
   encode(hmac('SYNTHETIC_PAN_510','dev_secret','sha256'),'hex'),'DEV_ENC_PAN_510','DEV_ENC_DEK_510',
   'IDC0020','Kavya Reddy','Investment Manager','Investment Banking',
   'B2','Mumbai','PERMANENT','2023-01-01',NULL,'ACTIVE');

-- ============================================================
-- STAGING TABLES FOR DOCUMENT GENERATION
-- ============================================================

CREATE TEMP TABLE _stints_b (
  emp_n        INT,
  emp_name     TEXT,
  emp_user_id  UUID,
  emp_uuid     UUID,
  tenant_id    UUID,
  employer     TEXT,
  designation  TEXT,
  doj          DATE,
  dol          DATE,
  is_alumni    BOOLEAN
);

INSERT INTO _stints_b VALUES
  -- ── Emp 501 Arjun Kapoor ────────────────────────────────────────────────
  (501,'Arjun Kapoor',   '30000000-0000-0000-0000-000000000501','50000000-0501-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Software Engineer',          '2016-01-01','2019-12-31',TRUE),
  (501,'Arjun Kapoor',   '30000000-0000-0000-0000-000000000501','50000000-0501-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Senior Financial Analyst',   '2020-01-01','2022-12-31',TRUE),
  (501,'Arjun Kapoor',   '30000000-0000-0000-0000-000000000501','50000000-0501-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Research Lead',              '2023-01-01',NULL,        FALSE),
  -- ── Emp 502 Meera Krishnan ──────────────────────────────────────────────
  (502,'Meera Krishnan', '30000000-0000-0000-0000-000000000502','50000000-0502-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Data Engineer',              '2016-01-01','2019-12-31',TRUE),
  (502,'Meera Krishnan', '30000000-0000-0000-0000-000000000502','50000000-0502-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Senior Risk Analyst',        '2020-01-01','2022-12-31',TRUE),
  (502,'Meera Krishnan', '30000000-0000-0000-0000-000000000502','50000000-0502-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Clinical Data Lead',         '2023-01-01',NULL,        FALSE),
  -- ── Emp 503 Siddharth Rao ───────────────────────────────────────────────
  (503,'Siddharth Rao',  '30000000-0000-0000-0000-000000000503','50000000-0503-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'DevOps Engineer',            '2016-01-01','2019-12-31',TRUE),
  (503,'Siddharth Rao',  '30000000-0000-0000-0000-000000000503','50000000-0503-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Compliance Analyst',         '2020-01-01','2022-12-31',TRUE),
  (503,'Siddharth Rao',  '30000000-0000-0000-0000-000000000503','50000000-0503-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Regulatory Affairs Manager', '2023-01-01',NULL,        FALSE),
  -- ── Emp 504 Natasha Verma ───────────────────────────────────────────────
  (504,'Natasha Verma',  '30000000-0000-0000-0000-000000000504','50000000-0504-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Product Analyst',            '2016-01-01','2019-12-31',TRUE),
  (504,'Natasha Verma',  '30000000-0000-0000-0000-000000000504','50000000-0504-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Investment Analyst',         '2020-01-01','2022-12-31',TRUE),
  (504,'Natasha Verma',  '30000000-0000-0000-0000-000000000504','50000000-0504-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'QA Lead',                    '2023-01-01',NULL,        FALSE),
  -- ── Emp 505 Rajesh Pillai ───────────────────────────────────────────────
  (505,'Rajesh Pillai',  '30000000-0000-0000-0000-000000000505','50000000-0505-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Financial Analyst',          '2016-01-01','2019-12-31',TRUE),
  (505,'Rajesh Pillai',  '30000000-0000-0000-0000-000000000505','50000000-0505-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Senior Research Scientist',  '2020-01-01','2022-12-31',TRUE),
  (505,'Rajesh Pillai',  '30000000-0000-0000-0000-000000000505','50000000-0505-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Senior Software Engineer',   '2023-01-01',NULL,        FALSE),
  -- ── Emp 506 Divya Menon ─────────────────────────────────────────────────
  (506,'Divya Menon',    '30000000-0000-0000-0000-000000000506','50000000-0506-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Risk Analyst',               '2016-01-01','2019-12-31',TRUE),
  (506,'Divya Menon',    '30000000-0000-0000-0000-000000000506','50000000-0506-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Clinical Data Analyst',      '2020-01-01','2022-12-31',TRUE),
  (506,'Divya Menon',    '30000000-0000-0000-0000-000000000506','50000000-0506-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Senior Data Engineer',       '2023-01-01',NULL,        FALSE),
  -- ── Emp 507 Aditya Gupta ────────────────────────────────────────────────
  (507,'Aditya Gupta',   '30000000-0000-0000-0000-000000000507','50000000-0507-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Compliance Analyst',         '2016-01-01','2019-12-31',TRUE),
  (507,'Aditya Gupta',   '30000000-0000-0000-0000-000000000507','50000000-0507-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Regulatory Affairs Associate','2020-01-01','2022-12-31',TRUE),
  (507,'Aditya Gupta',   '30000000-0000-0000-0000-000000000507','50000000-0507-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Staff Engineer',             '2023-01-01',NULL,        FALSE),
  -- ── Emp 508 Preethi Nambiar ─────────────────────────────────────────────
  (508,'Preethi Nambiar','30000000-0000-0000-0000-000000000508','50000000-0508-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Research Associate',         '2016-01-01','2019-12-31',TRUE),
  (508,'Preethi Nambiar','30000000-0000-0000-0000-000000000508','50000000-0508-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Senior Software Engineer',   '2020-01-01','2022-12-31',TRUE),
  (508,'Preethi Nambiar','30000000-0000-0000-0000-000000000508','50000000-0508-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Finance Manager',            '2023-01-01',NULL,        FALSE),
  -- ── Emp 509 Suresh Babu ─────────────────────────────────────────────────
  (509,'Suresh Babu',    '30000000-0000-0000-0000-000000000509','50000000-0509-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Clinical Data Analyst',      '2016-01-01','2019-12-31',TRUE),
  (509,'Suresh Babu',    '30000000-0000-0000-0000-000000000509','50000000-0509-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Senior Data Engineer',       '2020-01-01','2022-12-31',TRUE),
  (509,'Suresh Babu',    '30000000-0000-0000-0000-000000000509','50000000-0509-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Risk Manager',               '2023-01-01',NULL,        FALSE),
  -- ── Emp 510 Kavya Reddy ─────────────────────────────────────────────────
  (510,'Kavya Reddy',    '30000000-0000-0000-0000-000000000510','50000000-0510-0013-0000-000000000001','10000000-0000-0000-0000-000000000013','Bluestar Pharma Pvt Ltd',      'Regulatory Affairs Associate','2016-01-01','2019-12-31',TRUE),
  (510,'Kavya Reddy',    '30000000-0000-0000-0000-000000000510','50000000-0510-0011-0000-000000000001','10000000-0000-0000-0000-000000000011','Vertex Technologies Pvt Ltd', 'Lead Engineer',              '2020-01-01','2022-12-31',TRUE),
  (510,'Kavya Reddy',    '30000000-0000-0000-0000-000000000510','50000000-0510-0012-0000-000000000001','10000000-0000-0000-0000-000000000012','Indigo Capital Ltd',           'Investment Manager',         '2023-01-01',NULL,        FALSE);

-- Pan token lookup for emp501-510
CREATE TEMP TABLE _pan_b AS
  SELECT n, encode(hmac('SYNTHETIC_PAN_' || LPAD(n::text, 3, '0'), 'dev_secret', 'sha256'), 'hex') AS pan_token
  FROM generate_series(501, 510) AS n;

-- ============================================================
-- DOCUMENTS
-- ============================================================

-- ── OFFER LETTERS ────────────────────────────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-OFFER-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'OFFER_LETTER',
  (s.doj - INTERVAL '30 days')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/OFFER_LETTER/' || (s.doj - INTERVAL '30 days')::date::text || '.pdf',
  'prana-documents-dev',
  (128 + (s.emp_n * 7) % 200) * 1024,
  md5('sha256-b-offer-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',  jsonb_build_object('value', s.emp_name,     'confidence', 0.98),
    'employer_name',  jsonb_build_object('value', s.employer,     'confidence', 0.99),
    'designation',    jsonb_build_object('value', s.designation,  'confidence', 0.97),
    'date_of_joining',jsonb_build_object('value', s.doj::text,    'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj - INTERVAL '30 days')::timestamptz,
  (s.doj - INTERVAL '28 days')::timestamptz,
  'Offer_Letter.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n;

-- ── JOINING LETTERS ──────────────────────────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-JOIN-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'JOINING_LETTER', s.doj::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/JOINING_LETTER/' || s.doj::text || '.pdf',
  'prana-documents-dev',
  (96 + (s.emp_n * 11) % 150) * 1024,
  md5('sha256-b-join-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',   jsonb_build_object('value', s.emp_name,    'confidence', 0.98),
    'employer_name',   jsonb_build_object('value', s.employer,    'confidence', 0.99),
    'designation',     jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'date_of_joining', jsonb_build_object('value', s.doj::text,   'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  s.doj::timestamptz,
  (s.doj + INTERVAL '2 days')::timestamptz,
  'Joining_Letter.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n;

-- ── SALARY SLIPS (months 6, 18, 30 of each stint — capped at dol or today) ──
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-SLIP-' || s.emp_n::text || '-' || s.tenant_id::text || '-' || m.n::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'SALARY_SLIP',
  to_char(s.doj + ((m.n * 6) || ' months')::interval, 'YYYY-MM'),
  s.tenant_id::text || '/' || s.emp_uuid::text || '/SALARY_SLIP/' ||
    to_char(s.doj + ((m.n * 6) || ' months')::interval, 'YYYY-MM') || '.pdf',
  'prana-documents-dev',
  (64 + (s.emp_n * m.n * 13) % 128) * 1024,
  md5('sha256-b-slip-' || s.emp_n::text || '-' || s.tenant_id::text || '-' || m.n::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name,   'confidence', 0.98),
    'employer_name', jsonb_build_object('value', s.employer,   'confidence', 0.99),
    'designation',   jsonb_build_object('value', s.designation,'confidence', 0.96),
    'pay_period',    jsonb_build_object('value', to_char(s.doj + ((m.n * 6) || ' months')::interval, 'Month YYYY'), 'confidence', 0.99),
    'pf_deducted',   jsonb_build_object('value', 'Yes', 'confidence', 0.95),
    'tds_deducted',  jsonb_build_object('value', 'Yes', 'confidence', 0.93)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + ((m.n * 6) || ' months')::interval)::timestamptz,
  (s.doj + ((m.n * 6) || ' months')::interval + INTERVAL '3 days')::timestamptz,
  'Salary_Slip_' || to_char(s.doj + ((m.n * 6) || ' months')::interval, 'Mon_YYYY') || '.pdf'
FROM _stints_b s
JOIN _pan_b p ON p.n = s.emp_n
CROSS JOIN (VALUES (1),(2),(3)) AS m(n)
WHERE (s.doj + ((m.n * 6) || ' months')::interval)::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── FORM 16 (one per stint, if tenure ≥ 12 months) ──────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-F16-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'FORM_16',
  'FY:' || (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text
         || '-' || EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/FORM_16/FY_' ||
    (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text || '.pdf',
  'prana-documents-dev',
  (200 + (s.emp_n * 17) % 300) * 1024,
  md5('sha256-b-f16-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',  jsonb_build_object('value', s.emp_name, 'confidence', 0.99),
    'employer_name',  jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'financial_year', jsonb_build_object('value',
      (EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int - 1)::text || '-' ||
       EXTRACT(YEAR FROM s.doj + INTERVAL '1 year')::int::text, 'confidence', 0.99),
    'tds_deducted',   jsonb_build_object('value', 'Yes', 'confidence', 0.97)
  ),
  'ROUTED', FALSE, FALSE,
  (DATE_TRUNC('year', s.doj + INTERVAL '1 year') + INTERVAL '3 months')::timestamptz,
  (DATE_TRUNC('year', s.doj + INTERVAL '1 year') + INTERVAL '3 months 3 days')::timestamptz,
  'Form16.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── PF ACKNOWLEDGEMENTS ──────────────────────────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-PF-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'PF_ACKNOWLEDGEMENT', s.doj::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/PF_ACKNOWLEDGEMENT/' || s.doj::text || '.pdf',
  'prana-documents-dev',
  (48 + (s.emp_n * 5) % 80) * 1024,
  md5('sha256-b-pf-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name', jsonb_build_object('value', s.emp_name, 'confidence', 0.98),
    'employer_name', jsonb_build_object('value', s.employer, 'confidence', 0.99),
    'uan_number',    jsonb_build_object('value', '10' || LPAD((s.emp_n * 100000 + 234567)::text, 10, '0'), 'confidence', 0.96),
    'effective_date',jsonb_build_object('value', s.doj::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '30 days')::timestamptz,
  (s.doj + INTERVAL '32 days')::timestamptz,
  'PF_Acknowledgement.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n;

-- ── INCREMENT LETTERS (stints ≥ 12 months) ───────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-INC-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'INCREMENT_LETTER',
  (s.doj + INTERVAL '12 months')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/INCREMENT_LETTER/' ||
    (s.doj + INTERVAL '12 months')::date::text || '.pdf',
  'prana-documents-dev',
  (80 + (s.emp_n * 9) % 120) * 1024,
  md5('sha256-b-inc-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',  jsonb_build_object('value', s.emp_name,    'confidence', 0.98),
    'employer_name',  jsonb_build_object('value', s.employer,    'confidence', 0.99),
    'designation',    jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'effective_date', jsonb_build_object('value', (s.doj + INTERVAL '12 months')::date::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '12 months')::timestamptz,
  (s.doj + INTERVAL '12 months 3 days')::timestamptz,
  'Increment_Letter.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── PROMOTION LETTERS (stints ≥ 24 months) ───────────────────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-PROMO-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  'PROMOTION_LETTER',
  (s.doj + INTERVAL '24 months')::date::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/PROMOTION_LETTER/' ||
    (s.doj + INTERVAL '24 months')::date::text || '.pdf',
  'prana-documents-dev',
  (90 + (s.emp_n * 13) % 110) * 1024,
  md5('sha256-b-promo-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',   jsonb_build_object('value', s.emp_name,    'confidence', 0.98),
    'employer_name',   jsonb_build_object('value', s.employer,    'confidence', 0.99),
    'new_designation', jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'effective_date',  jsonb_build_object('value', (s.doj + INTERVAL '24 months')::date::text, 'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  (s.doj + INTERVAL '24 months')::timestamptz,
  (s.doj + INTERVAL '24 months 3 days')::timestamptz,
  'Promotion_Letter.pdf'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '24 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- ── RELIEVING + EXPERIENCE LETTERS (alumni stints only) ──────────────────────
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token,
  doc_type, doc_period, s3_key, s3_bucket,
  file_size_bytes, file_hash_sha256, virus_scan_status, nsfw_scan_status, csam_detected,
  resolution_method, resolution_confidence, extracted_fields,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
)
SELECT
  md5('B-' || lt.letter_type || '-' || s.emp_n::text || '-' || s.tenant_id::text)::uuid,
  s.tenant_id, s.emp_uuid, p.pan_token,
  lt.letter_type, s.dol::text,
  s.tenant_id::text || '/' || s.emp_uuid::text || '/' || lt.letter_type || '/' || s.dol::text || '.pdf',
  'prana-documents-dev',
  (70 + (s.emp_n * 7) % 100) * 1024,
  md5('sha256-b-' || lt.letter_type || '-' || s.emp_n::text || '-' || s.tenant_id::text),
  'CLEAN', 'CLEAN', FALSE, 'PAN_TOKEN_EXACT', 0.999,
  jsonb_build_object(
    'employee_name',    jsonb_build_object('value', s.emp_name,    'confidence', 0.98),
    'employer_name',    jsonb_build_object('value', s.employer,    'confidence', 0.99),
    'designation',      jsonb_build_object('value', s.designation, 'confidence', 0.97),
    'last_working_day', jsonb_build_object('value', s.dol::text,   'confidence', 0.99)
  ),
  'ROUTED', FALSE, FALSE,
  s.dol::timestamptz,
  (s.dol + INTERVAL '3 days')::timestamptz,
  lt.letter_type || '.pdf'
FROM _stints_b s
JOIN _pan_b p ON p.n = s.emp_n
CROSS JOIN (VALUES ('RELIEVING_LETTER'),('EXPERIENCE_LETTER')) AS lt(letter_type)
WHERE s.is_alumni = TRUE;

-- ============================================================
-- CAREER EVENTS
-- ============================================================

-- JOINED events — all 30 stints
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token, s.emp_user_id, s.emp_uuid, s.tenant_id,
  'JOINED', s.doj,
  'Joined ' || s.employer || ' as ' || s.designation,
  s.designation,
  CASE WHEN s.doj < '2020-01-01' THEN 'L1'
       WHEN s.doj < '2023-01-01' THEN 'L2' ELSE 'L3' END,
  TRUE,
  'Career milestone: joined ' || s.employer || ' marking continued professional growth.'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n;

-- EXITED events — alumni stints only
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token, s.emp_user_id, s.emp_uuid, s.tenant_id,
  'EXITED', s.dol,
  'Left ' || s.employer,
  s.designation, NULL, TRUE,
  'Concluded tenure at ' || s.employer || ' after ' ||
    ((s.dol - s.doj) / 365) || ' year(s). Strong exit record maintained.'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE s.is_alumni = TRUE;

-- INCREMENT events — stints ≥ 12 months
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token, s.emp_user_id, s.emp_uuid, s.tenant_id,
  'INCREMENT', (s.doj + INTERVAL '12 months')::date,
  'Annual increment at ' || s.employer,
  s.designation, NULL, TRUE,
  'Performance-linked increment received at ' || s.employer || '. Progression aligned with market benchmark.'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '12 months')::date <= COALESCE(s.dol, CURRENT_DATE);

-- PROMOTED events — stints ≥ 24 months
INSERT INTO career_event (
  pan_token, employee_user_id, employee_uuid, tenant_id,
  event_type, event_date, event_title, designation, grade, verified, insight_text
)
SELECT
  p.pan_token, s.emp_user_id, s.emp_uuid, s.tenant_id,
  'PROMOTED', (s.doj + INTERVAL '24 months')::date,
  'Promoted to ' || s.designation || ' at ' || s.employer,
  s.designation, NULL, TRUE,
  'Promotion to ' || s.designation || ' reflects consistent high performance and leadership growth.'
FROM _stints_b s JOIN _pan_b p ON p.n = s.emp_n
WHERE (s.doj + INTERVAL '24 months')::date <= COALESCE(s.dol, CURRENT_DATE);

COMMIT;
