# PRANA Mobile Rules
# Auto-loaded when editing prana-mobile/**

## Stack
- React Native + Expo SDK 56
- React Query (server state) + Zustand (UI state)
- Expo Router (file-based routing)
- EAS Build for production builds

## Privacy UI rules (non-negotiable)
- Raw ₹ salary figures: NEVER displayed — show insight text only ("Your salary is competitive for your band")
- PAN: NEVER displayed in any screen — not masked, not partial, not at all
- Document watermark: always visible on document preview — never removable by user
- Password-protected doc flow: prompt password → process in-memory → never cache decrypted bytes

## Auth flow
1. Phone number entry (E.164 format with `+91` prefix)
2. OTP sent via SMS → 6-digit entry → verify
3. JWT returned → stored in SecureStore (never AsyncStorage — not encrypted)
4. Refresh token: SecureStore, 7-day TTL
5. Biometric re-auth for document access (FaceID / fingerprint) — optional but enforced if enrolled

## Document access
- Documents served as decrypted bytes from API — never cached to device storage
- Watermark applied server-side before streaming — client cannot bypass
- Share flow: generates time-limited share token → recipient gets OTP → 10-min session

## Navigation structure (Expo Router)
```
app/
  (auth)/         ← unauthenticated screens
    login.tsx
    otp.tsx
  (app)/          ← authenticated screens, all protected
    vault/
    career/
    employers/
    activity/
    share/
    ask/           ← Ask PRANA chatbot
```

## 3 states required on every screen
Loading → skeleton (never spinner alone on mobile — too small)
Error → full-screen error with retry button
Empty → illustrated empty state with call-to-action

## EAS Build rules
- Never commit `.env` — use `eas.json` with environment references
- `eas build --profile production` for release — not expo publish
- OTA updates: allowed for JS changes, not for native module changes
- Always bump `version` in `app.json` before production build

## Performance
- FlatList for all lists — never ScrollView with .map() for long lists
- Image: use `expo-image` not React Native Image — better caching
- Never fetch on every render — always React Query with proper staleTime
