# PRANA Mobile — React Native Build Brief

This is the handoff document for continuing the React Native (Expo) build of
the PRANA mobile app on your laptop using Claude Code. It assumes:

- `PRANA_Mobile_App_Prototype.html` (18-screen HTML prototype) is in the
  project folder as a visual/structural reference
- `PRANA_Mobile_DesignLanguage.md` (motion/haptics/interaction spec) is in
  the project folder
- `prana-rn-vault-home/` (the Vault Home proof-of-concept) has been merged
  into a fresh Expo project — `tokens.ts`, `DocumentCard.tsx`,
  `StatCard.tsx`, `VaultNav.tsx`, `VaultHomeScreen.tsx` already exist and work

**Goal:** all 18 screens, working navigation, mock data, runnable via
`npx expo start` and buildable to APK via `eas build`.

---

## 1. Navigation structure

Two navigators, switched based on auth state (mock a simple `isAuthenticated`
boolean in a context/state store for now — no real backend).

```
RootNavigator
├── AuthStack (stack navigator, no tab bar)
│   ├── Splash            (screen 1)
│   ├── SignIn             (screen 2)
│   ├── TotpSetup           (screen 3 — conditional, see §3)
│   ├── TotpVerify           (screen 4)
│   ├── RegisterDevice        (screen 5)
│   ├── EnableFaceId            (screen 6)
│   ├── BiometricUnlock          (screen 7 — entry point for returning users)
│   └── PushApproval               (screen 8 — can also be a modal/overlay)
│
└── VaultTabs (bottom tab navigator — this IS the VaultNav component)
    ├── Vault    → VaultHomeStack
    │              ├── VaultHome        (screen 9, with screen 17/18 as states — see §4)
    │              ├── DocumentViewer    (screen 16)
    │              ├── SelfUpload         (screen 13)
    │              └── CreateShare         (screen 14)
    ├── Activity → ActivityScreen        (screen 11)
    ├── Career   → CareerScreen          (screen 12)
    ├── Shares   → SharesScreen          (new — see §6, currently only
    │                                      reachable via Vault → CreateShare)
    └── Settings → SettingsScreen        (screen 15)

Menu (screen 10) is NOT a tab — it's a modal/drawer triggered from the ☰
icon on any VaultTabs screen. Implement as a React Navigation modal screen
presented over VaultTabs, or a custom Modal component.
```

**Entry flow:** `Splash` → checks mock auth state → `SignIn` (new device) or
`BiometricUnlock` (returning device, has stored `device_credential`) →
successful auth → `VaultTabs`.

---

## 2. Screen → file mapping

| # | HTML screen | RN file | Notes |
|---|---|---|---|
| 1 | Splash — animated launch | `src/screens/auth/SplashScreen.tsx` | Port the SVG career-thread animation using `react-native-svg` + `react-native-reanimated`. This is the highest-effort single screen — budget extra time |
| 2 | Sign in — glass + gradient | `src/screens/auth/SignInScreen.tsx` | `expo-blur` for glass card; gradient orbs as flat opacity circles (see tokens.ts pattern) |
| 3 | Set up 2FA (conditional) | `src/screens/auth/TotpSetupScreen.tsx` | QR placeholder — use `react-native-qrcode-svg` if a real QR is wanted, or keep as styled placeholder for mock |
| 4 | Enter authenticator code | `src/screens/auth/TotpVerifyScreen.tsx` | OTP grid — consider `react-native-otp-entry` or build the 6-box grid manually (simple enough) |
| 5 | Register this device | `src/screens/auth/RegisterDeviceScreen.tsx` | Checklist card, text input for device name |
| 6 | Enable Face ID | `src/screens/auth/EnableFaceIdScreen.tsx` | Bio-orb + rotating ring — `Animated.loop` with rotate transform |
| 7 | Biometric unlock (returning) | `src/screens/auth/BiometricUnlockScreen.tsx` | Same bio-orb component as #6, reused |
| 8 | Push-approval login | `src/screens/auth/PushApprovalScreen.tsx` | Notification card + detail rows + deny/approve buttons |
| 9 | Vault home | `src/screens/vault/VaultHomeScreen.tsx` | **Already built** — extend with banner/empty states, see §4 |
| 10 | Menu | `src/screens/MenuModal.tsx` | Glassmorphic drawer, presented as modal |
| 11 | Activity log | `src/screens/vault/ActivityScreen.tsx` | Two `tl-card` sections (documents, login history) |
| 12 | Career history | `src/screens/vault/CareerScreen.tsx` | Career timeline + events list |
| 13 | Self-upload + consent | `src/screens/vault/SelfUploadScreen.tsx` | File picker (`expo-document-picker`) + bottom sheet for Layer 2 consent |
| 14 | Create share | `src/screens/vault/CreateShareScreen.tsx` | Form screen — radio/pills/text input |
| 15 | Settings | `src/screens/vault/SettingsScreen.tsx` | Grouped settings rows + toggles |
| 16 | Document viewer | `src/screens/vault/DocumentViewerScreen.tsx` | Dark viewer + watermark overlay (absolute-positioned rotated Text) |
| 17 | Vault home — new doc banner | *(state of #9)* | Add `DocBanner` component + bell badge — see §4 |
| 18 | Vault home — empty state | *(state of #9)* | Add `EmptyVaultState` component — see §4 |

---

## 3. Conditional auth flow (screen 3)

`TotpSetupScreen` only shows for accounts with no TOTP configured yet. In the
mock, drive this off a flag in mock data:

```ts
// src/mocks/auth.ts
export const mockUser = {
  hasTotpConfigured: false, // toggle to true to skip TotpSetupScreen
  // ...
};
```

`SignInScreen`'s "Continue" handler checks this flag and navigates to either
`TotpSetup` or directly to `TotpVerify`.

---

## 4. Vault Home — three states (screens 9, 17, 18)

Rather than three separate screens, `VaultHomeScreen.tsx` should accept mock
data that determines which state renders:

```ts
interface VaultHomeState {
  documents: Document[];           // empty array -> screen 18 (empty state)
  newDocumentNotification?: {       // present -> screen 17 (banner)
    title: string;
    subtitle: string;
    documentId: string;
  };
  stats: { documents: number; activeShares: number };
}
```

Render logic:
- `documents.length === 0` → render `<EmptyVaultState />` instead of the
  stat grid + document list
- `newDocumentNotification` present → render `<DocBanner />` above the stat
  grid, and add `<View style={styles.bellBadge}><Text>{count}</Text></View>`
  over the bell icon
- otherwise → screen 9's normal state

This keeps one screen file with three testable states via mock data swaps —
closer to how it'll actually behave in production (state-driven, not
route-driven).

---

## 5. Mock data shape

Create `src/mocks/` with the following files. Shapes are derived from
`PRANA_UserMgmt_DataArchitecture.html`'s table definitions — keep field names
aligned to the real schema (`source_type`, `self_upload_context`, etc.) so
the eventual API integration is a drop-in replacement, not a rewrite.

```
src/mocks/
├── user.ts        — mock employee_master + employee_user (name, vault URL, pan_token)
├── documents.ts   — mock document[] rows: { id, doc_type, title, source_type
│                     ('EMPLOYER_PUSH'|'EMPLOYEE_SELF_UPLOAD'|'THIRD_PARTY_VERIFIED'),
│                     issuer, received_at, icon_type ('salary'|'form16'|'invest') }
├── activity.ts    — mock document_access_log + audit_event rows for Activity screen
├── career.ts      — mock career_event[] + employer list for Career screen
├── devices.ts      — mock trusted_device[] for Settings (device list)
└── auth.ts         — hasTotpConfigured flag, mock credentials for SignIn
```

**Icon-to-gradient mapping** (extend `docIconGradients` in `tokens.ts` as new
document types appear — currently `salary` / `form16` / `invest` are defined;
e.g. an `experience-letter` or `relieving-letter` type would need a new
gradient + emoji pair).

---

## 6. Gaps to resolve during this build (carried over from design review)

These were flagged in `PRANA_Mobile_DesignLanguage.md` §10 as open items —
worth resolving as part of navigation/screen-building rather than leaving
implicit:

1. **Bell icon destination** — currently no screen for "notification list."
   Either build a minimal `NotificationsScreen` (list of unseen banners +
   security events) reachable from the bell, or have the bell scroll/
   highlight the relevant banner on Vault Home. Recommend the former for
   the "Shares" tab gap below to make sense structurally.
2. **Shares tab** — the bottom nav has a "Shares" item, but no screen 9-18
   is "list of my active shares" (only *creating* a share, screen 14).
   Build a simple `SharesScreen` listing active `share_token` rows with
   revoke actions — this is a real gap, not just a mock-data placeholder.
3. **Empty states for Activity/Career/Shares** — per design doc §8, reuse
   the `EmptyVaultState` pattern (gradient-outline illustration + title +
   sub + CTA) for these three screens when their mock data arrays are empty.

---

## 7. Build order (suggested)

1. **Scaffold navigation** — get `RootNavigator` → `AuthStack` /
   `VaultTabs` switching on a hardcoded boolean, with placeholder screens
   (just `<Text>ScreenName</Text>`) for all 18. Confirms the navigation
   shape is right before investing in any screen's visuals.
2. **Auth flow (1-8)** — these are mostly self-contained, dark-themed,
   share the `auth-screen`/`glass-card`/`btn-grad` pattern from
   `SignInScreen` (build this one first as the new pattern reference,
   alongside the existing `VaultHomeScreen` light-theme pattern).
3. **Vault Home states (9/17/18)** — extend the existing component per §4.
4. **Remaining vault screens (10-16)** — these share the light-theme
   `page-screen`/`form-card`/`tl-card` patterns; batch them together.
5. **Gaps (§6)** — Shares list, Notifications, empty states for the new
   screens.
6. **Polish pass against `PRANA_Mobile_DesignLanguage.md`** — haptics,
   micro-interaction springs, shimmer loading states, swipe actions. This
   is the "feel" layer and is reasonable to defer until the structural app
   is complete and navigable.
7. **EAS build** — `eas build -p android --profile preview` once steps 1-5
   are done and the app is navigable end-to-end, even if step 6 (polish) is
   incomplete. Getting an APK in hand early is useful for on-device review
   even before motion polish is finished.

---

## 8. Things that will need real decisions before backend integration

Flagged here so they're not forgotten once the mock-data version "works":

- **Push-approval (screen 8)** requires a real push notification + signature
  flow (APNs/FCM + Secure Enclave keypair, per `device_credential` in the
  architecture doc) — entirely mocked for now (a button that just navigates
  to VaultTabs)
- **Biometric unlock (screens 6/7)** needs `expo-local-authentication` for
  real Face ID/Touch ID/fingerprint — straightforward to wire up once the
  visual is built, but the mock version should still gate navigation behind
  a "fake success" button so the flow is testable without a real biometric
  prompt in Expo Go (Expo Go has limited biometric support; a dev build may
  be needed for full testing)
- **Document upload (screen 13)** needs `expo-document-picker` +
  `expo-file-system` for real file selection; mock with a hardcoded filename
  initially
- **Watermark (screen 16)** — the rotated repeating text pattern translates
  to an absolutely-positioned `<Text>` with `transform: [{ rotate: '-28deg' }]`
  and low opacity, same as the HTML. For real documents (PDFs), this would
  need to be rendered server-side into the PDF itself for shared copies —
  the in-app watermark is for the *preview*, not the exported file
