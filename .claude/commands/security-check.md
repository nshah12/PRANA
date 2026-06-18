# /security-check

Run a security review on a specific file or feature area.

## Checks to run

### Privacy contract
- [ ] Does any endpoint return raw ₹ salary figures?
- [ ] Does any endpoint return PAN / NIK in plaintext?
- [ ] Does any LLM prompt include raw figures in expected output?
- [ ] Does any cache key contain plaintext PAN? (must be pan_token only)

### Tenant isolation
- [ ] Is `tenant_id` derived from JWT claims — not request body or URL?
- [ ] Does every multi-tenant query have `WHERE tenant_id = $1` as first condition?
- [ ] Does ownership check exist before returning records?

### Auth
- [ ] Is auth dependency the FIRST thing in every endpoint?
- [ ] Are all role checks using the correct dependency (`require_oa`, `require_employee`)?
- [ ] Is the correct login surface used for each role?

### SQL
- [ ] Are all queries parameterized? No f-string SQL?
- [ ] Are column names verified against schema.sql?

### Sensitive data
- [ ] Are passwords/tokens logged anywhere?
- [ ] Are secrets in env vars — not source code?
- [ ] Are error messages masking sensitive field values?

### Response
- [ ] Does API response contain any hash, DEK, or secret field?
- [ ] Are password fields excluded from all SELECT queries that return to API?

## Arguments
File or feature to check: `$ARGUMENTS`
