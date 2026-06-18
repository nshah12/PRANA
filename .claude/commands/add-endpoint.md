# /add-endpoint

Create a new FastAPI endpoint for PRANA following all established patterns.

## Steps (execute in order, no skipping)

1. **Read schema first**
   - Open `prana-db/schema.sql`
   - Find every table this endpoint will touch
   - Copy exact column names — write nothing from memory

2. **Read the router file**
   - Find or create the router in `prana-api/routers/`
   - Check existing endpoints for patterns (auth dependencies, response shapes)

3. **Read the service file**
   - Find or create the service in `prana-api/services/`
   - Check existing method signatures

4. **Implement service method first**
   - Business logic in service class — zero Temporal imports
   - All DB calls with exact column names from schema
   - Explicit serialization: UUID→str, date→.isoformat(), JSONB→json.loads()

5. **Implement router handler**
   - Auth dependency first line
   - `tenant_id` from JWT claims only
   - Response wrapped: `{"items": [...], "total": N}` for collections
   - Specific error codes as strings: `"INVALID_STATE"` not human sentences

6. **Verify Kafka contract**
   - If this is an ingest/mutation endpoint: does it only do validate→S3→1 DB write→1 publish?
   - No audit writes, no workflow starts, no notifications in HTTP path

7. **Check security**
   - Ownership check: does this user own the record being accessed?
   - No raw PAN/salary in response

## Arguments
Describe what the endpoint should do: `$ARGUMENTS`
