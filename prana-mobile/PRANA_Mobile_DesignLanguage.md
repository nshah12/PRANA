# PRANA Mobile — Design Language & Implementation Specs

Companion reference to `PRANA_Mobile_App_Prototype.html` (18 screens). The
prototype shows static states; this document specifies the motion, feedback,
and interaction details that a static HTML mockup cannot demonstrate but that
materially affect how the app *feels* — benchmarked against Revolut, Apple
Wallet, PhonePe, and Razorpay's current mobile apps.

---

## 1. Design tokens (recap)

| Token | Value | Use |
|---|---|---|
| `--space` / `--space2` | `#0B0F1E` / `#131B33` | Dark auth screen backgrounds |
| `--grad-journey` | `linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)` | Signature gradient — CTAs, hero card, FAB, splash thread |
| `--surface` / card gray | `#FAFAF8` / `#F0EFEA` | Light screen background / document cards |
| Display / body / mono | Space Grotesk / Inter / DM Mono | Headings / body text / data, codes, hashes |
| Radius | 16–24px | All cards, buttons, sheets |

---

## 2. Haptics

Haptic feedback is invisible in any screenshot or HTML prototype but is one of
the largest contributors to "this app feels premium" in Revolut and Apple
Wallet. Every interactive element below should fire the indicated haptic
(iOS: `UIImpactFeedbackGenerator` / `UINotificationFeedbackGenerator`;
Android: `HapticFeedbackConstants`).

| Interaction | Haptic | Notes |
|---|---|---|
| Toggle switch (on/off) | Light impact | Fires on release, synced with the thumb's spring settle |
| Primary button tap (gradient CTA) | Light impact | On press-down, not release — feels more responsive |
| Biometric success (Face ID unlock, push-approval) | Success notification | Distinct from a generic tap — this is a "trust" moment |
| Biometric failure | Error notification | Paired with a shake animation on the orb (±6px, 3 cycles, 80ms each) |
| Document card long-press (opens swipe actions, §5) | Medium impact | Signals a mode change |
| Pull-to-refresh trigger point reached | Light impact | Fires once when the refresh threshold is crossed, not on every pixel of pull |
| Share link created successfully | Success notification | |
| Deny on push-approval | Medium impact | Deliberate weight — this is a security-relevant action |
| Swipe-to-share released past threshold | Light impact | |

**Anti-pattern to avoid:** haptics on every scroll tick or every list item
becoming visible — Android apps that over-haptic feel cheap, not premium.
Reserve haptics for state changes and confirmations only.

---

## 3. Micro-interactions (press, toggle, card states)

| Element | At rest | On press/active | Spec |
|---|---|---|---|
| Gradient CTA button (`.btn-grad`, `.btn-approve`) | Full opacity, resting shadow | Scale `0.97`, shadow reduces to 50% | `transition: transform 100ms ease-out, box-shadow 150ms` |
| Document card (`.doc-card`) | Flat | Scale `0.98`, background darkens ~3% | Same as above — cards should feel "pressable" even though the primary action is a tap-to-open |
| Toggle (`.toggle2`) | Thumb at rest position | Thumb travels with `cubic-bezier(.34,1.56,.64,1)` (the same spring used for `sheetUp`/`popIn`), 220ms | Slight overshoot-and-settle, not a linear slide |
| FAB (`.vault-fab`) | Static | Scale `0.92` on press, returns with spring | Consider a brief rotation (+15deg) on press for personality — optional |
| Bell icon, new notification arrives | Static | Single shake: rotate ±8deg, 3 cycles over 400ms, then settle | Triggered when `bell-badge` count increments — draws the eye without being annoying |
| Bottom nav item selection | Icon + label in `--ink3` | Icon scales to `1.1` and color transitions to `--indigo` over 150ms | The active state shouldn't just snap — a brief scale pop reinforces the tap registered |

---

## 4. Loading & skeleton states

Currently absent from the prototype — every screen shows a fully-loaded state.
Two loading patterns are needed:

### 4.1 Cold start (app launch → vault home)
After the splash animation (screen 1) completes and authentication succeeds
(screens 6/7/8), Vault Home should show a **skeleton state** for up to ~600ms
while data loads — not a spinner.

- Hero card: render the gradient shape immediately (it's static content), but
  the URL/meta text area shows a shimmer bar (`rgba(255,255,255,.3)`,
  animated gradient sweep, 1.2s loop)
- Stat cards: gray placeholder boxes (`#F0EFEA`) where the numbers will appear,
  same shimmer
- Document cards: 2-3 skeleton cards with shimmer placeholders for icon,
  title, and meta lines — same dimensions as real `.doc-card` so there's no
  layout shift when real content arrives

**Shimmer spec:** `background: linear-gradient(90deg, #F0EFEA 25%, #E8E6DF 50%, #F0EFEA 75%); background-size: 200% 100%; animation: shimmer 1.2s ease-in-out infinite;` with `@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }`

### 4.2 Pull-to-refresh
Vault Home, Activity, and Career screens support pull-to-refresh.

- Pull reveals the gradient (`--grad-journey`) as a circular progress
  indicator, not a generic platform spinner — reinforces brand at a moment
  the user is actively engaging
- Haptic fires once at the trigger threshold (see §2)
- On release past threshold: brief scale-pulse on the refreshed content
  (stat numbers, new document count) to draw attention to what changed

---

## 5. Swipe actions on document cards

Currently, accessing share/download for a document requires opening it.
PhonePe and Razorpay both support swipe-left on list items for quick actions —
worth adopting for `.doc-card` given a 16+ document vault.

**Swipe-left reveals two actions**, each a 64px-wide colored panel sliding in
from the right edge of the card:

| Action | Color | Icon | Behavior |
|---|---|---|---|
| Share | `--indigo` background, white icon | ↗ | Opens Create Share (screen 14) pre-populated with this document selected |
| Download | `--emerald` background, white icon | ⤓ | Triggers download; for self-uploaded docs, no watermark (own copy) |

- Swipe threshold: revealing both actions requires ~40% card width swipe;
  releasing before that snaps back
- Haptic: light impact when threshold is crossed (action becomes "armed")
- Tapping elsewhere on the card while actions are revealed dismisses them
  (standard iOS swipe-cell behavior)

**Accessibility note:** swipe actions must have an equivalent long-press menu
or three-dot menu for users relying on assistive touch / screen readers — this
should not be the *only* path to share/download.

---

## 6. Hero card shimmer / parallax (Vault Home)

The gradient hero card (`.vault-hero`) is currently static. Two
low-cost additions used by Revolut and Apple Wallet on their card surfaces:

- **On-load shimmer sweep:** a single diagonal light sweep (white,
  `opacity: .15`, 45deg, 200ms) crosses the card once when Vault Home first
  renders — signals "this is a premium surface," not decoration that repeats
- **Scroll parallax:** as the user scrolls the document list, the hero card
  translates upward at ~50% of scroll speed and the `vault-topbg` gradient
  background at ~30% — creates subtle depth. Cap the effect so the hero card
  never scrolls fully out of view; it should settle into a compact "pinned"
  state (URL only, no meta line) once scrolled past ~80px, similar to
  Apple Wallet's card-to-strip collapse

---

## 7. New-document banner (screen 17) — behavioral notes

The banner introduced in screen 17 is the highest-priority addition from a
product-value standpoint — it's the moment PRANA's core promise ("your
documents arrive automatically") becomes visible to the user.

- **Trigger:** any `document` row with `source_type = 'EMPLOYER_PUSH'` and
  `created_at` within the last 24h *that the user hasn't yet viewed*
  generates one banner. Multiple new documents collapse into a single banner
  ("3 new documents from NPCI") rather than stacking
- **Dismissal:** tapping ✕ marks the banner's documents as "seen" (does not
  delete/hide the document itself — it remains in the list with its
  highlighted border, per screen 17, for one session)
- **Persistence:** the banner reappears on next app open if the user dismissed
  it without tapping into the document — i.e. dismissal ≠ acknowledgment.
  Only opening the document marks it fully "seen"
- **Bell badge count** = count of unseen employer-pushed documents +
  unseen security-relevant activity (new device registered, etc.) — these are
  two different notification *types* and should be visually distinguishable
  in the notification list (separate from the drawer menu, screen 10), which
  is itself a gap: currently tapping 🔔 has no defined destination. **Open
  item:** either (a) the bell opens a dedicated notification list, or (b) it
  scrolls to/highlights the relevant banner on Vault Home. Recommend (a) for
  scalability once notification types multiply.

---

## 8. Empty states — beyond Vault Home (screen 18)

Screen 18 covers Vault Home's empty state. The same pattern (illustration +
title + sub + actionable next step) should extend to:

- **Activity, zero events:** "Nothing here yet — activity will appear as your
  documents are accessed, shared, or updated."
- **Career, single employer only:** not really "empty," but the timeline
  connector line (§ design system) should not render for a single node —
  avoid a line that goes nowhere
- **Shares, zero active shares:** illustration of the share icon + "You
  haven't shared anything yet" + CTA to Vault to select documents

Each empty state should reuse the `--grad-journey` gradient in its
illustration (outline style, per screen 18) to keep a consistent "this brand"
feeling even when there's no data — this is what makes Revolut's empty states
feel designed rather than default.

---

## 9. Settings — danger zone treatment

Currently, "Remove" on a trusted device (screen 15) is a small ghost button
inline with other rows — easy to miss, but also easy to mis-tap given its
proximity to informational rows.

**Recommendation:** any destructive/security-sensitive action (remove device,
revoke share early, log out of all devices) should:

- Sit in a visually separated group with a subtle red-tinted background
  (`rgba(239,68,68,.04)`) and `border: 1px solid rgba(239,68,68,.12)`
- Require a confirmation sheet (reuse `.sheet-glass` pattern from screen 13)
  for "Remove device" and "Log out of all devices" — not for simple toggles
- Use `--red` (`#EF4444`) text color only for the destructive action label,
  not for the row icon background (keep icon backgrounds neutral so the
  red doesn't read as an error state on a row that's just informational)

---

## 10. Open items / not yet specced

These were identified during the benchmark but are lower priority than
items 2–9 above:

- **Notification center** destination for the bell icon (§7)
- **Search** across documents — not present in any screen; useful once a
  vault has 30+ documents across multiple employers
- **Dark mode for light screens (9–15)** — screens 1–8 and 16 are already
  dark; a full dark mode would need gray-card equivalents (`#1C2747` family)
  for screens 9–15
- **Biometric failure / fallback flow** — screen 7 shows success only; a
  failed Face ID attempt (3x) falling back to App PIN is not yet designed
