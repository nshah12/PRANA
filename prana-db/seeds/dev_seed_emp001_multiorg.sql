-- Multi-org seed for employee 001 (30000000-0000-0000-0000-000000000001)
-- Adds ABCD Bank (alumni, Jul 2016 – Feb 2020) and PQRS Fintech (active, Mar 2020 – present)
-- TechCorp stays as the primary/current employer (Jan 2020 – present, mark as alumni)
-- Career: ABCD Bank → TechCorp → PQRS Fintech (current)

-- ── Step 1: Make TechCorp alumni (dol = 2023-06-30) ─────────────────────────
UPDATE employee_master
SET dol = '2023-06-30', status = 'INACTIVE'
WHERE employee_uuid = '40000000-0000-0000-0001-000000000001';

-- ── Step 2: ABCD Bank — alumni (Jul 2016 – Feb 2020) ───────────────────────
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id, pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department, grade, doj, dol, status,
  vault_completeness, can_push, created_at, updated_at
) VALUES (
  '40000000-0000-0000-0001-000000000002',
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002', -- ABCD Bank
  'pan_token_emp001',
  'enc_pan_emp001',
  'enc_dek_emp001',
  'ABCD0181',
  'Rahul Sharma',
  'Junior Analyst',
  'Retail Banking',
  'G2',
  '2016-07-01',
  '2020-01-31',
  'INACTIVE',
  72,
  FALSE,
  NOW() - INTERVAL '8 years',
  NOW()
) ON CONFLICT (employee_uuid) DO NOTHING;

-- ABCD Bank docs
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token, doc_type, doc_period,
  s3_key, s3_bucket, file_size_bytes, file_hash_sha256,
  virus_scan_status, nsfw_scan_status, csam_detected,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
) VALUES
  -- Appointment Letter
  ('d0000000-abcd-0001-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'APPOINTMENT_LETTER', '2016-07',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/appt_2016.pdf',
   'prana-docs-dev', 204800, 'abc123hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '8 years', NOW() - INTERVAL '8 years', 'Appointment_Letter_ABCD_2016.pdf'),

  -- Salary Slips (3 months)
  ('d0000000-abcd-0002-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'SALARY_SLIP', '2019-11',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/slip_2019_11.pdf',
   'prana-docs-dev', 102400, 'def456hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '5 years 2 months', NOW() - INTERVAL '5 years 2 months', 'Salary_Slip_Nov_2019.pdf'),

  ('d0000000-abcd-0003-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'SALARY_SLIP', '2019-12',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/slip_2019_12.pdf',
   'prana-docs-dev', 102400, 'ghi789hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '5 years 1 month', NOW() - INTERVAL '5 years 1 month', 'Salary_Slip_Dec_2019.pdf'),

  -- Form 16
  ('d0000000-abcd-0004-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'FORM_16', 'FY:2019-20',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/form16_fy2019.pdf',
   'prana-docs-dev', 307200, 'jkl012hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '5 years', NOW() - INTERVAL '5 years', 'Form_16_FY2019-20_ABCD.pdf'),

  -- Relieving Letter
  ('d0000000-abcd-0005-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'RELIEVING_LETTER', '2020-01',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/relieving_2020.pdf',
   'prana-docs-dev', 153600, 'mno345hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '5 years', NOW() - INTERVAL '5 years', 'Relieving_Letter_ABCD_2020.pdf'),

  -- Experience Letter
  ('d0000000-abcd-0006-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   '40000000-0000-0000-0001-000000000002',
   'pan_token_emp001',
   'EXPERIENCE_LETTER', '2020-01',
   'tenants/abcd/emp/40000000-0000-0000-0001-000000000002/exp_2020.pdf',
   'prana-docs-dev', 153600, 'pqr678hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '5 years', NOW() - INTERVAL '5 years', 'Experience_Letter_ABCD_2020.pdf');

-- ── Step 3: PQRS Fintech — active (Feb 2024 – present) ─────────────────────
INSERT INTO employee_master (
  employee_uuid, employee_user_id, tenant_id, pan_token, enc_pan, enc_dek,
  emp_id_org, full_name, designation, department, grade, doj, dol, status,
  vault_completeness, can_push, created_at, updated_at
) VALUES (
  '40000000-0000-0000-0001-000000000003',
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000003', -- PQRS Fintech
  'pan_token_emp001',
  'enc_pan_emp001',
  'enc_dek_emp001',
  'PQRS0042',
  'Rahul Sharma',
  'Senior Software Engineer',
  'Engineering',
  'L5',
  '2024-02-01',
  NULL,
  'ACTIVE',
  88,
  TRUE,
  NOW() - INTERVAL '1 year 4 months',
  NOW()
) ON CONFLICT (employee_uuid) DO NOTHING;

-- PQRS Fintech docs
INSERT INTO document (
  document_id, tenant_id, employee_uuid, pan_token, doc_type, doc_period,
  s3_key, s3_bucket, file_size_bytes, file_hash_sha256,
  virus_scan_status, nsfw_scan_status, csam_detected,
  pipeline_status, is_self_upload, is_deleted, pushed_at, routed_at, original_filename
) VALUES
  -- Offer Letter
  ('d0000000-pqrs-0001-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'OFFER_LETTER', '2024-01',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/offer_2024.pdf',
   'prana-docs-dev', 204800, 'stu901hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '17 months', NOW() - INTERVAL '17 months', 'Offer_Letter_PQRS_2024.pdf'),

  -- Appointment Letter
  ('d0000000-pqrs-0002-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'APPOINTMENT_LETTER', '2024-02',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/appt_2024.pdf',
   'prana-docs-dev', 204800, 'vwx234hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '16 months', NOW() - INTERVAL '16 months', 'Appointment_Letter_PQRS_2024.pdf'),

  -- Salary Slips (recent months)
  ('d0000000-pqrs-0003-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'SALARY_SLIP', '2025-03',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/slip_2025_03.pdf',
   'prana-docs-dev', 102400, 'yza567hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '3 months', NOW() - INTERVAL '3 months', 'Salary_Slip_Mar_2025.pdf'),

  ('d0000000-pqrs-0004-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'SALARY_SLIP', '2025-04',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/slip_2025_04.pdf',
   'prana-docs-dev', 102400, 'bcd890hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '2 months', NOW() - INTERVAL '2 months', 'Salary_Slip_Apr_2025.pdf'),

  ('d0000000-pqrs-0005-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'SALARY_SLIP', '2025-05',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/slip_2025_05.pdf',
   'prana-docs-dev', 102400, 'efg123hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '1 month', NOW() - INTERVAL '1 month', 'Salary_Slip_May_2025.pdf'),

  -- Increment Letter
  ('d0000000-pqrs-0006-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'INCREMENT_LETTER', 'FY:2025-26',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/increment_2025.pdf',
   'prana-docs-dev', 153600, 'hij456hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '2 months', NOW() - INTERVAL '2 months', 'Increment_Letter_PQRS_FY2025.pdf'),

  -- Form 16
  ('d0000000-pqrs-0007-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   '40000000-0000-0000-0001-000000000003',
   'pan_token_emp001',
   'FORM_16', 'FY:2024-25',
   'tenants/pqrs/emp/40000000-0000-0000-0001-000000000003/form16_fy2025.pdf',
   'prana-docs-dev', 307200, 'klm789hash',
   'CLEAN', 'CLEAN', FALSE,
   'ROUTED', FALSE, FALSE,
   NOW() - INTERVAL '1 month', NOW() - INTERVAL '1 month', 'Form_16_FY2024-25_PQRS.pdf');
