-- Migration 026: Add tenant_id to employee_consent for per-org consent scoping.
--
-- Architecture principle violated in 025: in a multi-tenant SaaS system, tenant_id
-- belongs in every table by default. Compelling reason required to OMIT it, not to add it.
-- employee_user is the one valid exception (cross-tenant identity anchor).
-- employee_consent was missing tenant_id, causing us to create a redundant alumni_consent
-- table. This migration fixes that properly.
--
-- Consent model after this migration:
--   tenant_id IS NULL  → global consent (document_processing, insight_generation, peer_benchmark)
--   tenant_id IS NOT NULL → per-org consent (alumni_visibility for a specific past employer)
--
-- Unique enforcement via two partial indexes (standard pattern for nullable unique columns):
--   - Global: UNIQUE (employee_user_id, purpose) WHERE tenant_id IS NULL
--   - Per-org: UNIQUE (employee_user_id, purpose, tenant_id) WHERE tenant_id IS NOT NULL

-- Step 1: Drop the old unique constraint
ALTER TABLE employee_consent DROP CONSTRAINT IF EXISTS uq_consent_employee_purpose;

-- Step 2: Add tenant_id (nullable — NULL = global, non-NULL = per-org)
ALTER TABLE employee_consent
  ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE;

-- Step 3: Add contact-sharing flags (used by alumni_visibility purpose only)
ALTER TABLE employee_consent
  ADD COLUMN IF NOT EXISTS share_mobile BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE employee_consent
  ADD COLUMN IF NOT EXISTS share_email  BOOLEAN NOT NULL DEFAULT TRUE;

-- Step 4: Partial unique indexes replace the old single unique constraint
CREATE UNIQUE INDEX IF NOT EXISTS uq_consent_global
  ON employee_consent (employee_user_id, purpose)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consent_per_org
  ON employee_consent (employee_user_id, purpose, tenant_id)
  WHERE tenant_id IS NOT NULL;

-- Step 5: Covering index for CHRO query — "all alumni who consented for this tenant"
CREATE INDEX IF NOT EXISTS idx_consent_tenant_purpose
  ON employee_consent (tenant_id, purpose, is_active)
  WHERE tenant_id IS NOT NULL;

-- Step 6: Drop the now-redundant alumni_consent table created in migration 025
DROP TABLE IF EXISTS alumni_consent;
