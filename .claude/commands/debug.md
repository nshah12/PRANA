# /debug

Systematically debug a PRANA issue. Always diagnose outside-in — never start with code.

## Diagnostic order (never skip levels)

### Level 1 — Is the right process running?
```powershell
netstat -ano | findstr ":8000"   # how many PIDs? should be exactly 1
Get-Process python* | Select-Object Id, Name
```
- If 2+ PIDs: kill ALL, verify port free, start fresh
- If 0 PIDs: start the server
- Only proceed to Level 2 when exactly 1 PID owns the port

### Level 2 — Is the request reaching the right place?
- Open browser Network tab
- Check: exact URL, method, request headers, Authorization token
- Check: is there a proxy (Kong) in between?
- Check: is response from cache?

### Level 3 — What is the exact raw response?
- Log or curl the exact response body
- Is the shape what the frontend expects? (`data.items` vs `data` bare array)
- Is there a serialization error? (UUID, datetime, JSONB as string)

### Level 4 — Code inspection
Only here after levels 1-3 confirmed. Check:
- Column names match `prana-db/schema.sql` exactly
- Method names match the actual class definition
- Endpoint URL matches the actual router decorator

## Arguments
Describe the symptom: `$ARGUMENTS`
