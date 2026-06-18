-- Mark all dev-seeded documents as ROUTED so they appear in the employee vault.
-- Run after dev_seed.sql and any Python seed scripts.
UPDATE document
SET pipeline_status = 'ROUTED',
    routed_at = NOW() - INTERVAL '1 hour'
WHERE pipeline_status IN ('QUEUED', 'ENCRYPTING', 'SCANNING', 'EXTRACTING', 'RESOLVING')
  AND is_deleted = FALSE;
