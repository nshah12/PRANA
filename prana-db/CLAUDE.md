@../CLAUDE.md

# PRANA DB — Schema & Migrations

## What lives here
```
prana-db/
  schema.sql        ← Full YugabyteDB DDL, 19 tables, correct FK order
  migrations/       ← Numbered migration files (001_*.sql, 002_*.sql ...)
  seeds/            ← Dev/test seed data only — never production data
```

## Database
- **Engine:** YugabyteDB (PostgreSQL-compatible distributed SQL)
- **Regions:** ap-south-1 (Mumbai) primary, ap-south-2 (Hyderabad) replica
- **Driver:** asyncpg (used by prana-api and prana-ai)
- **Schema file:** `schema.sql` — source of truth for all 19 tables

## 26 Tables — 11 Layers
| Layer | Tables |
|-------|--------|
| 1 Core Identity | `employee_user` |
| 2 Multi-tenancy | `tenant` |
| 3 Employee Records | `employee_master`, `employee_master_history`, `career_event` |
| 4 User Management | `oa_user`, `chro_user`, `portal_admin` |
| 5 Session & Auth | `user_session`, `backup_code`, `login_attempt_log`, `trusted_device`, `device_credential`, `elevation_request`, `account_status_event`, `api_key` |
| 6 Documents & Sharing | `document`, `share_token`, `document_access_log` |
| 7 Exceptions & Requests | `exception_queue`, `document_request` |
| 8 Compliance & DPDP | `dpdp_grievance`, `nominee` |
| 9 Audit & Security | `audit_event`, `anomaly_event`, `kms_key_log` |
| 10 Analytics & Platform Ops | `pa_platform_summary`, `vault_health_score`, `salary_band` |
| 11 Platform Config | `platform_config`, `tenant_config` |

## Schema Ownership Rules
- `schema.sql` is the canonical DDL — it must always be deployable from scratch on a fresh YugabyteDB cluster
- Never alter tables directly in production. All changes go through a numbered migration in `migrations/`
- Migration naming: `001_add_career_event.sql`, `002_add_salary_band.sql` — sequential, never gap
- Each migration must be idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`)
- `tenant.home_region` is IMMUTABLE after provisioning — no migration may alter it post-insert

## YugabyteDB Specifics
- Distributed primary keys: prefer `UUID` over serial integers (avoids hotspot on single tablet)
- `audit_event` is PARTITION BY RANGE(occurred_at) — monthly partitions, managed by `RetentionWorkflow`
- No `SERIAL` columns — use `gen_random_uuid()` as default for UUID PKs
- `JSONB` columns (`extracted_fields`, `metadata`) — index with `GIN` only if query pattern is known
- Row-level security (RLS) is enforced on all tenant-scoped tables — `tenant_id` must be in every WHERE clause on those tables

## Migration Rules
- Run migrations via `prana-api` service at startup (Alembic or custom runner)
- Never run DDL inside a Temporal workflow or activity
- Rollback: every migration file must have a commented `-- ROLLBACK:` section at the bottom
- Test migrations against a local YugabyteDB Docker instance before merging

## Seeds (`seeds/`)
- Dev seeds only: 1 platform, 2 tenants, 5 employees, sample documents
- Never commit real PAN numbers, real salaries, or real employee names to seeds
- Seed data uses `pan_token = HMAC('TEST_PAN_001', 'dev_secret')` — clearly synthetic
