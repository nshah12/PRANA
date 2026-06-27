-- Migration 030: add webhook_secret to hrms_connector_config
-- Stores the HMAC secret for validating incoming webhook payloads from HRMS systems.
-- Additive: nullable so existing rows are unaffected.

ALTER TABLE hrms_connector_config
    ADD COLUMN IF NOT EXISTS webhook_secret TEXT;   -- plaintext OK: low-sensitivity shared secret, not a DEK
