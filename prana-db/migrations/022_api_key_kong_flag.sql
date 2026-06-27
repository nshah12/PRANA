-- Migration 022: add kong_consumer_registered to api_key
-- Tracks whether this API key's HMAC credential has been registered in Kong.
-- FALSE on insert; set TRUE by provision_tenant activity after Kong Admin API call.
-- PA console can filter on FALSE to find tenants needing Kong re-registration.

BEGIN;

ALTER TABLE api_key
  ADD COLUMN IF NOT EXISTS kong_consumer_registered BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_api_key_kong_unregistered
  ON api_key(tenant_id)
  WHERE kong_consumer_registered = FALSE AND status = 'ACTIVE';

COMMIT;

-- ROLLBACK:
-- BEGIN;
-- DROP INDEX IF EXISTS idx_api_key_kong_unregistered;
-- ALTER TABLE api_key DROP COLUMN IF EXISTS kong_consumer_registered;
-- COMMIT;
