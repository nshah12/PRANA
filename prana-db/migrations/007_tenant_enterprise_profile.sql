-- 007_tenant_enterprise_profile.sql
-- Enterprise-grade tenant profile fields.
-- Extends tenant table with legal identity, addresses, contacts, DPDP, workforce, and contract data.

ALTER TABLE tenant
  ADD COLUMN IF NOT EXISTS brand_name                 VARCHAR(200),
  ADD COLUMN IF NOT EXISTS entity_type                VARCHAR(30),
  ADD COLUMN IF NOT EXISTS pan_entity                 VARCHAR(10),
  ADD COLUMN IF NOT EXISTS tan                        VARCHAR(10),
  ADD COLUMN IF NOT EXISTS incorporation_date         DATE,
  ADD COLUMN IF NOT EXISTS roc_jurisdiction           VARCHAR(50),
  -- Addresses: {line1, line2, city, district, state, pincode}
  ADD COLUMN IF NOT EXISTS reg_address                JSONB,
  ADD COLUMN IF NOT EXISTS corp_address               JSONB,
  -- Primary contact: {name, designation, email, mobile}
  ADD COLUMN IF NOT EXISTS primary_contact            JSONB,
  -- DPDP Act 2023 — mandatory for DPDP compliance
  ADD COLUMN IF NOT EXISTS dpo_name                   VARCHAR(100),
  ADD COLUMN IF NOT EXISTS dpo_email                  VARCHAR(150),
  ADD COLUMN IF NOT EXISTS grievance_officer_name     VARCHAR(100),
  ADD COLUMN IF NOT EXISTS grievance_officer_email    VARCHAR(150),
  ADD COLUMN IF NOT EXISTS dpa_accepted_at            TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS dpa_version                VARCHAR(20) DEFAULT '1.0',
  -- Workforce profile
  ADD COLUMN IF NOT EXISTS industry                   VARCHAR(50),
  ADD COLUMN IF NOT EXISTS employee_headcount_band    VARCHAR(20),
  ADD COLUMN IF NOT EXISTS payroll_frequency          VARCHAR(20) DEFAULT 'MONTHLY',
  ADD COLUMN IF NOT EXISTS fiscal_year_start          VARCHAR(10) DEFAULT 'APRIL',
  ADD COLUMN IF NOT EXISTS hrms_system                VARCHAR(50),
  ADD COLUMN IF NOT EXISTS document_ingestion_method  VARCHAR(30) DEFAULT 'PORTAL_UPLOAD',
  ADD COLUMN IF NOT EXISTS additional_domains         TEXT[],
  -- Statutory registrations (OA fills post-activation)
  ADD COLUMN IF NOT EXISTS pf_registration            VARCHAR(30),
  ADD COLUMN IF NOT EXISTS esic_registration          VARCHAR(20),
  -- Branding (OA edits via Org Profile)
  ADD COLUMN IF NOT EXISTS logo_url                   TEXT,
  ADD COLUMN IF NOT EXISTS brand_colour               VARCHAR(7),
  ADD COLUMN IF NOT EXISTS support_email              VARCHAR(150),
  -- PA-managed contract and SLA
  ADD COLUMN IF NOT EXISTS sla_tier                   VARCHAR(20) DEFAULT 'STANDARD',
  ADD COLUMN IF NOT EXISTS onboarding_tier            VARCHAR(20) DEFAULT 'ASSISTED',
  ADD COLUMN IF NOT EXISTS contract_type              VARCHAR(20) DEFAULT 'ANNUAL',
  ADD COLUMN IF NOT EXISTS account_manager            VARCHAR(100);

-- ROLLBACK:
-- ALTER TABLE tenant
--   DROP COLUMN IF EXISTS brand_name,
--   DROP COLUMN IF EXISTS entity_type,
--   DROP COLUMN IF EXISTS pan_entity,
--   DROP COLUMN IF EXISTS tan,
--   DROP COLUMN IF EXISTS incorporation_date,
--   DROP COLUMN IF EXISTS roc_jurisdiction,
--   DROP COLUMN IF EXISTS reg_address,
--   DROP COLUMN IF EXISTS corp_address,
--   DROP COLUMN IF EXISTS primary_contact,
--   DROP COLUMN IF EXISTS dpo_name,
--   DROP COLUMN IF EXISTS dpo_email,
--   DROP COLUMN IF EXISTS grievance_officer_name,
--   DROP COLUMN IF EXISTS grievance_officer_email,
--   DROP COLUMN IF EXISTS dpa_accepted_at,
--   DROP COLUMN IF EXISTS dpa_version,
--   DROP COLUMN IF EXISTS industry,
--   DROP COLUMN IF EXISTS employee_headcount_band,
--   DROP COLUMN IF EXISTS payroll_frequency,
--   DROP COLUMN IF EXISTS fiscal_year_start,
--   DROP COLUMN IF EXISTS hrms_system,
--   DROP COLUMN IF EXISTS document_ingestion_method,
--   DROP COLUMN IF EXISTS additional_domains,
--   DROP COLUMN IF EXISTS pf_registration,
--   DROP COLUMN IF EXISTS esic_registration,
--   DROP COLUMN IF EXISTS logo_url,
--   DROP COLUMN IF EXISTS brand_colour,
--   DROP COLUMN IF EXISTS support_email,
--   DROP COLUMN IF EXISTS sla_tier,
--   DROP COLUMN IF EXISTS onboarding_tier,
--   DROP COLUMN IF EXISTS contract_type,
--   DROP COLUMN IF EXISTS account_manager;
