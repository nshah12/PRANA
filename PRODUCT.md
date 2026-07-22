# Product

## Register

product

## Users

**Employers (primary purchaser):**
OA-Operator and OA-Admin — HR operations staff at Indian companies. Mid-career professionals, not designers or engineers. Use the portal daily for document push, exception resolution, and compliance reporting. Work under time pressure; every screen must be scannable in 10 seconds. Also: CHRO (weekly digest, vault health), CFO (payroll intelligence, anomaly alerts), Tenant CISO (security audit trail, account locks).

**Employees (primary beneficiary, mobile-first):**
Salaried and gig workers across India. Most are not tech-savvy. They arrive because their employer pushed documents. The moment that converts them from passive recipient to active user is when they realise PRANA is useful outside their current job — loan applications, background verification, tax filing, job changes.

**Portal Admin (PRANA internal staff):**
Platform operators who onboard tenants, manage API keys, and resolve cross-tenant incidents. Power users; density and information richness matter more than simplicity.

## Product Purpose

PRANA is a career document vault for Indian workers. Employers push employment documents (salary slips, Form 16, offer letters) via a Portal or HRMS API. Employees access a lifelong, verified record of their career — across every employer, every job change.

The AI pipeline extracts insights from documents without ever storing raw salary figures or PAN. The vault persists through job changes, resignations, and retirement. The employee owns it forever.

Success looks like: an employee uses PRANA to share verified employment history with a bank, a recruiter scans a Career Passport QR at an interview, a CHRO can answer "what is our Form-16 issuance rate?" in 10 seconds.

## Brand Personality

Trusted · Precise · Empowering

PRANA is not a government portal (anxiety-inducing, cluttered), not a fintech app (cold, transactional), and not a generic SaaS tool (forgettable purple). It is the quiet confidence of having your documents in order. Think: a well-organised filing cabinet that happens to be intelligent.

Voice: direct, jargon-free, respectful of the user's time. Never patronising. India-native without being provincial.

## Anti-references

- **Government / e-filing portals (MCA, TRACES, EPFO)** — the exact anxiety PRANA replaces. Cluttered, dated, form-heavy, institutional gray. PRANA must feel like relief after these.
- **Generic SaaS (Notion, Linear, Clerk)** — minimal white + purple accent, rounded cards, startup aesthetic. Too casual for a product handling legal employment documents.
- **Bank / wealth management UI (HDFC NetBanking, Zerodha)** — navy-and-gold institutional palette. PRANA is for workers, not wealth. Approachable, not exclusive.
- **Consumer super-apps (CRED, Groww)** — bright, gamified, dopamine-driven. PRANA has a Career Score but the core product handles compliance documents — tone must stay composed.

## Design Principles

1. **Composure under complexity.** Six roles, 50+ screens, sensitive data. The UI must feel calm at every zoom level. Density without clutter; hierarchy without decoration.

2. **Trust is shown, not claimed.** Don't badge "secure" on every screen. Show it through precise timestamps, audit trails visible to the right roles, encryption indicators exactly where they matter — nowhere else.

3. **India-native, not India-flavoured.** Hindi/English bilingual documents, EPFO, PAN, Form 16, Aadhaar — these are first-class concepts, not edge cases. The product should feel like it was built for Indian HR, not adapted from a Western SaaS template.

4. **Employee dignity.** Salary figures never shown. PAN never shown. Career insights surface the meaning, not the raw data. Every screen an employee sees should feel like it respects their privacy — not as a legal checkbox but as a design choice.

5. **Time is the primary constraint.** OA-Operators upload in bulk. CHROs check digests between meetings. Employees open the app when they need a document urgently (loan application, job interview). Every primary action must be reachable in 2 taps or less.

## Accessibility & Inclusion

- WCAG 2.1 AA minimum; target AA on all text, AAA on critical data (document status, alert badges)
- Multilingual: interface in English, document content in Hindi/English/regional scripts — render correctly, never garble
- Reduced motion support required on all animations (employees on low-end Android devices)
- Touch targets minimum 44px on employee-facing screens (mobile-first)
- Color must never be the sole indicator of status — always paired with icon or label
