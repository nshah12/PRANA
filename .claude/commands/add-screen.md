# /add-screen

Create a new screen for prana-portal or prana-mobile following established patterns.

## Steps (execute in order)

1. **Read the spec first**
   - Open the relevant spec HTML file in `prana-docs/`
   - Portal: `PRANA_Portal_v52.html` — read the full JS-embedded content for this screen
   - Mobile: `PRANA_UserMgmt_DataArchitecture_v25.html`
   - Note exact: role access, fields shown, actions available, empty states

2. **Read the backend router**
   - Open the API router file for exact endpoint URL and response shape
   - Never assume endpoint names or response keys

3. **Implement with all 3 states**
   - Loading: skeleton or spinner
   - Error: meaningful message with retry option
   - Empty: empty state UI with call-to-action

4. **Auth guard**
   - Which roles can access this screen?
   - RequireAuth with role check — redirect to correct login for that role

5. **React Query setup**
   - `queryKey` includes all filter/pagination params
   - `onError` handler on all mutations
   - Invalidate related queries after mutations

6. **No nested touch targets**
   - One Pressable / clickable element per card
   - Parent removes wrapper when child becomes interactive

7. **Register in router**
   - Add route to `App.tsx` or layout router
   - Add to sidebar nav if applicable

## Arguments
Describe the screen: `$ARGUMENTS`
