@../CLAUDE.md

# PRANA Mobile App

## Stack
- React Native + Expo SDK 56
- Expo Router (file-based routing) — **always read versioned docs at https://docs.expo.dev/versions/v56.0.0/**
- TypeScript strict mode

## Folder Structure
```
src/
  app/
    (auth)/        — sign-in, otp, set-password, enable-face-id, consent, activate
    (vault)/       — 4-tab nav: vault, activity, career, ask + data-rights, settings, shares
  mocks/           — mock data (replace with API calls when backend is ready)
  prana-theme/     — tokens.ts: colors, fonts, gradJourney, radius
  context/         — AuthContext
  prana-screens/   — legacy screens (being migrated to app/ route structure)
```

## Route Groups
- `(auth)` — unauthenticated flows
- `(vault)` — authenticated, 4-tab bottom nav (vault, activity, career, ask)

## Theme Tokens (always import from `@/prana-theme/tokens`)
```ts
import { colors, fonts, gradJourney, radius } from '@/prana-theme/tokens';
```
- `gradJourney` — the primary brand gradient (use for avatars, CTAs, highlights)
- Do NOT use `Alert` from react-native — use inline UI state instead

## Coding Rules
- No Pressable wrapping entire cards when there is an explicit action icon (eye, share) — only the icon is tappable
- Route pushes: use `router.push('/(vault)/data-rights')` pattern with full group prefix
- Hidden tabs registered as `<Tabs.Screen name="x" options={{ href: null }} />`
- Modal screens: `presentation: 'modal', animation: 'slide_from_bottom'`
- Always check for unused imports before committing — TypeScript will warn

## Privacy UI Rules
- Career chart: show growth index (baseline 100) in P (percentile) mode; actual ₹ values in A (actual) mode — employee viewing their OWN data is fine
- Document processing screen: show 5-step animated trace ("Decrypting in memory…", "Raw data discarded…")
- Never show raw salary figures in push notifications or activity feed
- Watermark format: `PRANA-{doc_short}-{emp_short}-{YYYYMMDD}-{HHMM}-{4char_random}`

## EAS Build
- Package: `in.prana.mobile`
- EAS Project ID: `61e6ba15-4372-4f04-a3a7-ca01c6e85934`
- Preview profile → APK (internal distribution)
- Production profile → AAB (Play Store)
- Command: `npx eas-cli build --profile preview --platform android`

## Testing (Jest + jest-expo + React Native Testing Library)
- **Run:** `npm test` (or `npm run test:watch`). Config: `jest.config.js`, setup: `jest.setup.js`.
- **Stack:** `jest-expo` preset (RN/Expo transforms) + `@testing-library/react-native` (RTL).
- **Naming:** co-locate as `*.test.ts` / `*.test.tsx` next to the file under test.
- **Path aliases:** `jest.config.js` `moduleNameMapper` mirrors tsconfig `@/* → src/*`,
  plus an explicit `@/i18n → i18n/` (the locale module lives at repo root, not `src/`).
- **Native mocks:** `jest.setup.js` mocks `expo-secure-store` and AsyncStorage (its official
  Jest mock). Add project-specific native-module mocks there.
- **⚠ RTL v14 gotcha #1 (async render):** `render`, `rerender`, and `unmount` are **async** —
  you MUST `await render(<C />)`. Destructuring `render(...)` synchronously yields a Promise
  with no query methods (`getByText is not a function`).
- **⚠ RTL v14 gotcha #2 (multi-render commit flake):** on this React-19 stack, a component
  render that runs immediately after a `fireEvent`-heavy test in the same file can occasionally
  commit an **empty tree** (`toJSON()` is null, queries find nothing) — even though it passes in
  isolation. Mitigations that work: prefer the queries returned by `await render(...)` over the
  global `screen`; `afterEach(async () => { await cleanup() })`; keep render-only assertions in
  one test rather than many tiny ones; and if a test only flakes when it runs last, reorder it
  earlier. This is an upstream RTL-v14/React-19 issue, not a project bug.
- **⚠ RTL v14 gotcha #3 (screens with looping `Animated`):** a screen that starts an
  `Animated.loop(...)` in `useEffect` (e.g. a pulsing icon) is especially prone to gotcha #2 —
  the perpetual animation callbacks interact with `act()` across tests in the same file. Fix:
  use the async `findBy*` queries (via the object returned by `await render(...)`, not sync
  `getBy*`) for every lookup in that file, including the very first field you fill in — the
  retry-until-found behavior absorbs the animation-induced re-renders. Plain screens without
  looping animations are fine with `getBy*`.
- **Pattern:** wrap components that use React Query in a `QueryClientProvider`
  (`new QueryClient({ defaultOptions: { queries: { retry: false } } })`), same as prana-portal.
- First reference tests: `i18n/index.test.ts` (pure logic) and
  `src/prana-components/StatCard.test.tsx` (RTL render).
