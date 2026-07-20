-- Migration 019: Add tenant.domain_verified_at.
-- workflows/activities.py's check_dns_txt_record activity already writes this
-- column on successful DNS TXT verification, but it never existed in the
-- schema — the UPDATE would fail at runtime. Needed for the PA Onboarding
-- Queue's "awaiting domain verification" elapsed/remaining time display.
-- Run inside a transaction. Safe to re-run (idempotent).
-- ROLLBACK: ALTER TABLE tenant DROP COLUMN IF EXISTS domain_verified_at;

BEGIN;

INSERT INTO schema_migrations (version, description) VALUES ('019', 'tenant_domain_verified_at')
ON CONFLICT (version) DO NOTHING;

ALTER TABLE tenant
    ADD COLUMN IF NOT EXISTS domain_verified_at TIMESTAMPTZ;

COMMIT;
