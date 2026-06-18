# /seed

Seed test data for a specific PRANA feature area.

## Steps

1. **Read schema for tables involved**
   - Open `prana-db/schema.sql`
   - Note NOT NULL columns — every one needs a value
   - Note FK constraints — seed parent rows before child rows
   - Note PK type (UUID vs serial) — use `gen_random_uuid()` for UUIDs

2. **Check existing seeds**
   - Read `prana-db/seeds/` for existing data to avoid conflicts
   - Note existing tenant_ids, employee_uuids to reference consistently

3. **Seed order (FK dependency order)**
   - tenant → oa_user → employee_user → employee_master → document → child tables

4. **Connection**
   ```powershell
   # YugabyteDB on Docker
   docker exec -it prana-yugabyte ysqlsh -U yugabyte -d prana
   ```

5. **Verify after seeding**
   - Query the seeded rows to confirm they exist
   - Hit the API endpoint to confirm data comes through correctly

## Common seed data reference
- TechCorp tenant_id: check `prana-db/seeds/`
- Test employee phone: `+919000000001`
- Test OA admin: `admin@techcorp.in`

## Arguments
What feature area needs seeding: `$ARGUMENTS`
