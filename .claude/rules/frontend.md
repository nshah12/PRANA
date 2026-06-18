# PRANA Frontend Rules
# Auto-loaded when editing prana-portal/** or prana-mobile/**
# ENFORCEMENT: scripts/enforce_rules.py — FRONTEND-01 (no nested Pressables), FRONTEND-02 (useQuery needs error state)
# Run /enforce before any PR merge.

## Stack
- Portal: React.js (Vite + React Router v6) + shadcn/ui + Tailwind + React Query + Zustand
- Mobile: React Native / Expo SDK 56 + React Query
- Auth: JWT in httpOnly cookie — never localStorage

## Every data-fetching component must handle 3 states
1. **Loading** — skeleton or spinner — never blank screen
2. **Error** — meaningful message — never silent failure
3. **Empty** — empty state UI — never blank list

## React Query rules
- `queryKey` must include ALL filter params — cache must invalidate when filters change
- `onError` on every mutation — never swallow errors silently
- Invalidate related queries after mutation success
- `staleTime` for non-realtime data

## Component rules
- NEVER nest Pressable / TouchableOpacity / clickable elements — one touch target per card
- Lift state when two siblings need same data
- Props drilling 3+ levels → use context or Zustand

## Forms
- Disable submit while request in-flight — prevent double-submit
- Field-level errors next to the field — not just top-level banner
- Clear sensitive fields (password, OTP) after submit

## Auth — 3 login surfaces (NEVER mix up)
| Path | Login URL | Refresh endpoint |
|------|-----------|-----------------|
| `/org/*` | `/org/login` | `/auth/org/refresh` |
| `/admin/*` | `/admin/login` | `/auth/admin/refresh` |
| `/emp/*` | `/emp/login` | `/auth/employee/refresh` |

- RequireAuth redirects based on path prefix — never hardcode `/org/login` for all roles
- Auth interceptor uses role-appropriate refresh endpoint — not a single hardcoded URL
- Redirect after login to originally-requested URL

## API calls
- Always verify exact endpoint URL from backend router file — never assume from naming
- Use params objects — never string concatenation for URLs
- Never put sensitive data in query string params
- Response shape: check `data?.items?.map` pattern to know what key frontend expects

## Portal roles
OA-Operator, OA-Admin, CHRO, CFO, CISO → `oa_user` table → `/org/login`
Portal Admin → `portal_admin` table → `/admin/login`
Employee → `employee_user` table → `/emp/login`
