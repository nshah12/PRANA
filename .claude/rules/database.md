# PRANA Database Rules
# Auto-loaded when editing prana-db/** or any file containing SQL
# ENFORCEMENT: scripts/enforce_rules.py — DB-01 (no f-string SQL), DB-02 (no SELECT *), DB-03 (no bare except)
# Run /enforce before any PR merge. Violations block deployment.

## FIRST RULE — always read schema before writing SQL
Before writing ANY query, open `prana-db/schema.sql` and find the exact CREATE TABLE block.
Copy column names — never write them from memory.
This rule has caused 4+ bugs. It is not optional.

## Database
- YugabyteDB (PostgreSQL-compatible) — dual region ap-south-1 + ap-south-2
- asyncpg driver — all queries async
- Schema: `prana-db/schema.sql` — 26 tables

## Query rules
- Always parameterized — `WHERE col = $1` never f-string SQL
- Never `SELECT *` — name every column
- Always `ORDER BY` when using `LIMIT/OFFSET` — without it, pagination is non-deterministic
- Always `LIMIT` on list queries — never unbounded SELECT
- Multi-tenant: `WHERE tenant_id = $1` always first condition
- Soft delete: always `AND is_deleted = FALSE`
- Use `EXISTS` not `COUNT(*)` for boolean checks

## Transactions
- Any operation touching 2+ tables = transaction
- Read-then-write (check-then-insert) = transaction
- Never partial-write across tables

## NULLs
- `IS NULL` / `IS NOT NULL` — never `= NULL`
- `COALESCE(col, default)` for fallback values
- NOT NULL schema columns: always provide a value

## Migrations (`prana-db/migrations/`)
- Additive only — never DROP COLUMN or ALTER TYPE on live table
- Add column nullable → backfill → add NOT NULL constraint
- Always test rollback path

## Key table notes
- `document_access_log` PK = `access_id` (not `log_id`)
- `document` table uses `pushed_at` (not `created_at`)
- `employee_master` has one row per tenant per employee — multi-org employees have multiple rows
- Career queries must use subquery across ALL `employee_master` rows — never filter by single `employee_uuid`
