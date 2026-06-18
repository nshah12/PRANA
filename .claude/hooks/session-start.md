# Session Start Checklist
# This runs automatically at the start of every session

## Before writing a single line of code, complete ALL of these:

1. **Read MEMORY.md** — recall what was decided, what failed, what patterns apply
2. **Read the relevant spec** for the feature area — never implement from memory
3. **Glob actual files** — never assert what's built or not built without checking
4. **Run gap check** — re-read CLAUDE.md and ask:
   - What external systems are mentioned that have no rule yet?
   - What will break in production that no current rule prevents?
   - What did the last session leave unfinished?
5. **Check running processes** — if API work is planned:
   - `netstat -ano | findstr ":8000"` — exactly 1 PID?
   - If not clean: fix before touching any code

## Never skip this. The user should never have to remind you.
