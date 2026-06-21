# PRANA Dev Credentials

> Reset script: `cd prana-api && python scripts/reset_dev.py`  
> All passwords: **`Prana@Admin0124`**  
> TOTP (OA users + Portal Admin): **fixed dev secret `JBSWY3DPEHPK3PXP`** — add this manually to your authenticator app once, it works for ALL accounts forever across every reset.  
> Add to authenticator: open app → Add account → Enter setup key → type `JBSWY3DPEHPK3PXP` → name it "PRANA Dev"  
> Employee OTP: SMS-based — use `123456` in dev

---

## Employee Credentials (Mobile App)

Login flow: enter mobile → receive OTP (use `123456`) → vault opens

| # | Name | Mobile | Email | Password | Career depth |
|---|------|--------|-------|----------|-------------|
| 001 | Rahul Sharma | `+919000000001` | emp001@test.prana | DevEmp@123 | 1 org — TechCorp |
| 002 | Priya Nair | `+919000000002` | emp002@test.prana | DevEmp@123 | 2 orgs |
| 003 | Amit Patel | `+919000000003` | emp003@test.prana | DevEmp@123 | 3 orgs |
| 004 | Deepika Reddy | `+919000000004` | emp004@test.prana | DevEmp@123 | 4 orgs |
| 005 | Kiran Kumar | `+919000000005` | emp005@test.prana | DevEmp@123 | 5 orgs |
| 006 | Sneha Joshi | `+919000000006` | emp006@test.prana | DevEmp@123 | 6 orgs |
| 007 | Rohan Mehta | `+919000000007` | emp007@test.prana | DevEmp@123 | 7 orgs |
| 008 | Ananya Singh | `+919000000008` | emp008@test.prana | DevEmp@123 | 8 orgs |
| 009 | Vikram Iyer | `+919000000009` | emp009@test.prana | DevEmp@123 | 9 orgs |
| 010 | Pooja Sharma | `+919000000010` | emp010@test.prana | DevEmp@123 | 10 orgs |

**Emp 002 note:** `force_reset=TRUE` — must change password on first login (tests the reset flow).

---

## Career History per Employee

| Emp | Org 1 (oldest) | Org 2 | Org 3 | Org 4 | Org 5 | Org 6 | Org 7 | Org 8 | Org 9 | Org 10 (current) |
|-----|---------------|-------|-------|-------|-------|-------|-------|-------|-------|-----------------|
| 001 | — | — | — | — | — | — | — | — | — | TechCorp 2024 |
| 002 | — | — | — | — | — | — | — | — | Nexus 2021 | TechCorp 2024 |
| 003 | — | — | — | — | — | — | — | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 004 | — | — | — | — | — | — | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 005 | — | — | — | — | — | Pinnacle 2012 | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 006 | — | — | — | — | Horizon 2009 | Pinnacle 2012 | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 007 | — | — | — | Aurora 2006 | Horizon 2009 | Pinnacle 2012 | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 008 | — | — | Cascade 2003 | Aurora 2006 | Horizon 2009 | Pinnacle 2012 | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 009 | — | ABCD Bank 2000 | Cascade 2003 | Aurora 2006 | Horizon 2009 | Pinnacle 2012 | Zephyr 2015 | Meridian 2018 | Nexus 2021 | TechCorp 2024 |
| 010 | PQRS 2000 | ABCD Bank 2003 | Cascade 2006 | Aurora 2009 | Horizon 2012 | Pinnacle 2015 | Zephyr 2018 | Meridian 2021 | Nexus 2021 | TechCorp 2024 |

Each org stint includes: Offer Letter + Joining Letter + 3× Salary Slips + Form 16 + PF Acknowledgement  
Alumni stints add: Relieving Letter + Experience Letter  
Stints > 12 months add: Increment Letter  
Emp 005–010, stints > 24 months add: Promotion Letter

---

## Portal OA Credentials

Login URL: `http://localhost:3000/org/login`  
**All passwords: `Prana@Admin0124`**

**First login flow:** enter email → enter password → portal detects TOTP not configured → shows QR code → scan with authenticator app → enter 6-digit code to confirm → TOTP registered. All subsequent logins: email + password + live 6-digit TOTP code.

### TechCorp Solutions — 86 documents (tenant with all 5 roles)

| Role | Email | Password | What they can do |
|------|-------|----------|-----------------|
| OA-Admin | admin@techcorp.in | Prana@Admin0124 | Full admin: users, exceptions, elevations |
| OA-Operator | operator@techcorp.in | Prana@Admin0124 | Upload docs, view exception queue |
| CHRO | chro@techcorp.in | Prana@Admin0124 | Vault completeness, workforce digest |
| CFO | cfo@techcorp.in | Prana@Admin0124 | Financial analytics, anomaly acknowledgement |
| CISO | ciso@techcorp.in | Prana@Admin0124 | Security dashboard, access logs, force-logout |

### Other Orgs with Documents

| Org | Email | Password | Documents |
|-----|-------|----------|-----------|
| Nexus Software | admin@nexussoftware.in | Prana@Admin0124 | 96 |
| Meridian Capital | admin@meridiancapital.in | Prana@Admin0124 | 86 |
| Zephyr Analytics | admin@zephyranalytics.in | Prana@Admin0124 | 76 |
| Pinnacle Manufacturing | admin@pinnacleindia.in | Prana@Admin0124 | 66 |
| Horizon Consulting | admin@horizonconsulting.in | Prana@Admin0124 | 55 |
| Aurora Pharma | admin@aurorapharma.in | Prana@Admin0124 | 44 |
| Cascade Retail | admin@cascaderetail.in | Prana@Admin0124 | 33 |
| ABCD Bank | admin@abcdbank.in | Prana@Admin0124 | 22 |
| PQRS Fintech | admin@pqrsfintech.in | Prana@Admin0124 | 11 |

> Note: `admin@technova.in` and other `@*.in` test org admins have 0 documents — use the orgs above.

---

## Portal Admin Credential

Login URL: `http://localhost:3000/admin/login`

| Email | Password | Note |
|-------|----------|------|
| admin@prana.in | (set on first login) | force_reset=TRUE — hash is placeholder in dev_seed.sql |

---

## TOTP Setup (per user, per device)

Each OA user gets their own unique TOTP secret generated by PRANA on first login. The portal shows a QR code — scan it, the authenticator app stores that user's private secret, and from then on supplies the rolling 6-digit code at login.

There is no shared secret and no bypass. Each of the 16 OA users has their own authenticator entry.

---

## Mobile App Testing without APK — Expo Go

No APK needed. Testers use **Expo Go** (free app):

1. **Install Expo Go** from Play Store (Android) or App Store (iOS)
2. Dev starts the app with tunnel mode:
   ```bash
   cd prana-mobile
   npx expo start --tunnel
   ```
3. A QR code appears in the terminal
4. **Android:** open Expo Go → scan QR  
   **iOS:** open Camera app → scan QR → tap the Expo Go banner
5. The full PRANA mobile app loads — live reload works, no APK needed

**For sharing across the internet** (not just local WiFi):  
`--tunnel` creates a public Ngrok URL automatically. Share the QR or the `exp://` URL with testers anywhere.

**For persistent preview builds** (closer to production):
```bash
npx eas update --branch preview --message "v0.1 demo"
```
Testers open the `exp://` link in Expo Go — no build required, OTA update.

**Expo Go limitations:** native modules not included in Expo Go will not work (e.g., biometric auth `expo-local-authentication` prompts may behave differently). For a full production-identical test, use `eas build --profile preview` to get a shareable `.apk` / `.ipa`.
