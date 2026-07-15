-- 039_audit_role_revoke.sql
--
-- Closes the gap documented in schema.sql's audit_event comment: the
-- "REVOKE UPDATE, DELETE ON audit_event FROM app_role" note was never
-- executed as real DDL, and app_role never existed. Until now, the app's
-- own DB credentials (the "yugabyte" superuser in dev) could UPDATE/DELETE
-- audit_event rows directly — Immudb's dual-write (see services/immudb_service.py)
-- can PROVE a row was altered after the fact, but nothing stopped the alteration
-- itself. This migration creates a least-privilege role the app actually runs
-- as, and REVOKEs its ability to mutate/delete audit history.
--
-- Prerequisite: apply this BEFORE pointing prana-api's DB_USER/DB_PASSWORD at
-- prana_app_role (config.py's new default). Applying this migration does not
-- change what the app connects as by itself — that's controlled by
-- DB_USER/DB_PASSWORD env vars (docker-compose.yml / .env).

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'prana_app_role') THEN
    -- Dev-only default password, matching the pattern of other dev secrets
    -- (immudb/immudb, dev-secret, etc). config.py's fail-closed production
    -- guard refuses to boot with this password (or as this role's dev
    -- default at all) once app_env=production.
    CREATE ROLE prana_app_role LOGIN PASSWORD 'prana_app_role';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE prana TO prana_app_role;
GRANT USAGE ON SCHEMA public TO prana_app_role;

-- Broad day-to-day privileges — the app needs full CRUD on every table except
-- the one carve-out below.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prana_app_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO prana_app_role;

-- Any table created after this migration also grants prana_app_role CRUD by
-- default, so future migrations don't need to remember to re-grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prana_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO prana_app_role;

-- The carve-out: audit_event is append-only by policy. INSERT (AuditConsumer's
-- dual-write path) still works; UPDATE/DELETE no longer do, even if the app's
-- own credentials are compromised, misused, or hit a SQL-injection bug elsewhere.
REVOKE UPDATE, DELETE ON audit_event FROM prana_app_role;

-- Periodic Immudb re-verification schedule (AuditIntegrityVerificationWorkflow,
-- Pattern 3 — Temporal Schedule). See workflows/audit_integrity.py.
INSERT INTO platform_config (config_key, config_value, value_type, description, min_value, max_value)
VALUES (
  'audit_integrity_check_interval_minutes', '60', 'DURATION_MINUTES',
  'How often AuditIntegrityVerificationWorkflow re-checks recent audit_event rows against Immudb',
  '15', '1440'
)
ON CONFLICT (config_key) DO NOTHING;

-- ROLLBACK:
-- DELETE FROM platform_config WHERE config_key = 'audit_integrity_check_interval_minutes';
-- GRANT UPDATE, DELETE ON audit_event TO prana_app_role;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM prana_app_role;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM prana_app_role;
-- REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM prana_app_role;
-- REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM prana_app_role;
-- REVOKE USAGE ON SCHEMA public FROM prana_app_role;
-- REVOKE CONNECT ON DATABASE prana FROM prana_app_role;
-- DROP ROLE IF EXISTS prana_app_role;
-- (Note: rolling back does not restore whatever DB_USER the app was using
-- before this migration — that's a separate env var change.)
