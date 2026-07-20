---
name: PRANA Design System
version: 1.0.0
updated: 2026-06-29
source: scanned from prana-portal/src/index.css + tailwind.config.ts + Landing.tsx + emp/
---

# Design

## Overview

PRANA is a career document vault for Indian workers — compliance-grade, privacy-first, multi-role. The visual language must feel like composed authority: calm enough that a CISO trusts it with audit trails, legible enough that a first-generation smartphone user finds their salary slip.

One surface spans two registers: the employer Portal (dense, data-rich, product register) and the employee vault (simpler, dignity-forward, also product). The Landing page is the one brand surface. Design decisions must hold across all three.

**Current state:** functional, coherent tokens, but overdone on gradient text and decorative eyebrows. The system has bones; it needs restraint.

## Colors

### Palette

| Token | Hex | Usage |
|---|---|---|
| `--shell` | `#0F172A` | Sidebar, dark sections, code surfaces |
| `--canvas` | `#F8FAFC` | Page background |
| `--canvas2` | `#F1F5F9` | Secondary surfaces, section alternates |
| `--muted` | `#64748B` | Supporting text, labels, captions |
| `--border` | `#E2E8F0` | Dividers, card borders |
| `--ink` | `#0F172A` | Headings, primary text (same as shell) |
| `--ink-body` | `#334155` | Body text (slate-700, not slate-500) |

### Brand Accent

**Primary:** Indigo `#6366F1` (Tailwind indigo-500) — the one accent. Used for CTAs, focus rings, active states, primary links. Not for decorative gradients.

**Do not use:** the `GRAD` constant (`linear-gradient(135deg, #6366F1, #22D3EE, #34D399)`) as text fill anywhere. It is visually inconsistent — the indigo-to-cyan-to-emerald sweep reads as generic SaaS. Reserve gradient fills for: logo icon background, avatar backgrounds, progress bars (where direction carries meaning).

### Role Accent Colors

Semantic — one color per role, used for nav items, badges, and role-scoped UI only. Not for general decoration.

| Role | Color | Hex |
|---|---|---|
| Employee | Sky | `#0EA5E9` |
| OA-Operator | Emerald | `#10B981` |
| OA-Admin | Violet | `#8B5CF6` |
| Portal Admin | Amber | `#F59E0B` |
| CHRO | Pink | `#EC4899` |
| CFO | Indigo | `#6366F1` |
| CISO | Red | `#EF4444` |

### Status Colors

| Status | Color | Hex | Note |
|---|---|---|---|
| Success | Emerald | `#10B981` | Always pair with ✓ icon |
| Warning | Amber | `#F59E0B` | Always pair with ⚠ icon |
| Danger | Red | `#EF4444` | Always pair with ! icon |
| Info | Sky | `#0EA5E9` | Always pair with ℹ icon |

Color must never be the sole indicator of status — icon or label required.

### Contrast Rules

- Body text on `--canvas`: `#334155` (slate-700) minimum — not `#94A3B8` (slate-400). Slate-400 on white fails WCAG AA.
- Muted/caption text: `#64748B` (slate-500) on white — passes 4.5:1 barely. Use only for truly secondary content.
- Gray text on colored backgrounds: **banned**. Use a darker shade of the background's hue, or white. `text-slate-400` on `bg-red-500` is the most common violation in this codebase.

## Typography

### Font Stack

```css
font-family: Inter, system-ui, sans-serif;  /* all UI */
font-family: 'JetBrains Mono', 'Fira Code', monospace;  /* code, API keys, pan_token */
```

Single sans family. Distinction comes from weight (400/500/600/700/800), not a second typeface.

### Scale

| Level | Size | Weight | Usage |
|---|---|---|---|
| Display | `text-5xl`–`text-7xl` | 800 | Hero headline only — one per page |
| H1 | `text-4xl` | 800 | Section lead headings |
| H2 | `text-3xl` | 700 | Sub-section headings |
| H3 | `text-2xl` | 600 | Card group titles |
| H4 | `text-lg` / `text-xl` | 600 | Card headings |
| Body | `text-base` | 400 | Prose, descriptions |
| Small | `text-sm` | 400 | UI labels, secondary |
| Caption | `text-xs` | 400/500 | Timestamps, metadata |
| Mono | `text-sm` | 400 | Token values, IDs, API keys |

**Heading line length:** cap at 30ch on landing display heads (use `max-w` + `text-wrap: balance`).
**Body line length:** cap at 65–75ch.

### Eyebrow Kicker Rule

One deliberate eyebrow is voice. One on every section is AI scaffold.

**Allowed locations:**
- Hero: the "Now live · Enterprise pilot-ready" status badge. It earns its place — factual, not decorative.
- One other location where the section is genuinely a category shift (e.g. FAQ tabs introducing roles).

**Banned:** `text-xs font-bold text-indigo-500 tracking-widest uppercase` before every section heading. Remove or replace with typographic hierarchy alone.

## Elevation

### Shadows

```css
/* Flat / resting card */
box-shadow: none; border: 1px solid #E2E8F0;

/* Hover / interactive */
box-shadow: 0 4px 16px rgba(99,102,241,0.10);

/* Modal / dropdown */
box-shadow: 0 8px 32px rgba(15,23,42,0.12);

/* Dark surface (sidebar context) */
background: rgba(255,255,255,0.05);
border: 1px solid rgba(255,255,255,0.08);
```

### Z-Index Scale

```
1   — sticky nav
10  — tooltips
20  — dropdowns
30  — modals backdrop
40  — sidebar (EmpLayout: z-40 — correct)
50  — modals
100 — toasts / alerts
```

Never use arbitrary values like 999 or 9999.

## Components

### Buttons

**Primary CTA:**
```tsx
className="bg-indigo-600 text-white font-semibold rounded-xl px-6 py-3 hover:bg-indigo-700 transition-colors"
```
No gradient fill on primary CTAs. Indigo-600 solid. Hover: indigo-700.

**`GradBtn` (current) should be replaced.** The gradient button is the most common AI-generated SaaS tell in 2026. Replace with solid indigo.

**Secondary:**
```tsx
className="border border-slate-200 text-slate-700 font-medium rounded-xl px-5 py-2.5 hover:bg-slate-50 transition-colors"
```

**Destructive:**
```tsx
className="bg-red-50 text-red-600 border border-red-100 font-medium rounded-xl px-5 py-2.5 hover:bg-red-100 transition-colors"
```

### Cards

**Default card:**
```tsx
className="bg-white border border-slate-200 rounded-2xl p-5"
```
No colored side-stripe. No `border-l-4`. If accent is needed, use `border-t-2` with the relevant role color, or a tinted background (`bg-indigo-50/40`).

**Dark surface card (sidebar context):**
```tsx
className="bg-white/5 border border-white/8 rounded-xl px-4 py-3"
```

**Nested cards:** always wrong. If you find yourself writing a card inside a card, rethink the layout.

### FAQ Accordion

The current implementation is strong — keep it. Improvements:
- Replace `✕` text button with lucide `X` icon for consistent icon rendering
- Animate the answer panel with `max-height` transition instead of conditional render (prevents layout jump)

### Navigation (EmpLayout sidebar)

**Current issues:**
- 9 accent colors = chromatic overload. Limit to: employee primary (sky), and one muted tone for inactive states.
- Active state relies only on background tint — add `font-medium` (already there) and ensure icon contrast passes at WCAG AA against `rgba(14,165,233,0.15)`.
- No mobile breakpoint — **this is the P0 issue for employee UX.** Add a `<768px` hamburger + slide-over pattern.

**Proposed:**
```tsx
// Active nav item — simplified
style={{ background: 'rgba(14,165,233,0.12)' }}
// Icon active color: role color (sky for employee)
// Icon inactive color: #94A3B8 — only one muted tone, not 9 different hues
```

### Trust Strip / Stat Display

Replace gradient-text stat values with ink + accent weight:
```tsx
// Before (banned)
<div style={{ background: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' }}>14</div>

// After
<div className="text-3xl font-extrabold text-slate-900">14</div>
<div className="text-indigo-600 font-extrabold text-3xl">99.9%</div>  // only for the one most important stat
```

### Pipeline Status Steps (HIW_STEPS)

Replace `n: '01'`…`'06'` numbered badges with the step icon at larger size in the active state. Numbers add no information the card position doesn't already convey.

## Do's and Don'ts

### Do

- Use `text-indigo-600` (solid) for emphasis — it's warmer than gradient and passes contrast
- Use `border-t-2 border-indigo-200` on active/selected cards — subtle, not AI-ish
- Use `text-wrap: balance` on all h1–h3
- Show status with icon + color pair, always (never color alone)
- Use `font-bold` or `font-extrabold` to create hierarchy — typography earns what decoration wastes
- Use `bg-slate-50` + `border border-slate-100` for section alternates — gentle separation
- Use the gradient fill for avatar initials, logo icon bg, and progress bars only
- Keep role accent colors to sidebar nav, role badges, and role-scoped data cells only

### Don't

- **Don't** use `background-clip: text` with a gradient — ever
- **Don't** put an eyebrow kicker above every section heading
- **Don't** use numbered section markers (01/02/03) as decoration
- **Don't** use `border-l-4` colored stripe on cards
- **Don't** use gray text (`text-slate-400`) on colored backgrounds
- **Don't** render 9 different hue accents in a single nav sidebar
- **Don't** render a video placeholder with a non-functional play button on a live page
- **Don't** hardcode file paths (`prana-docs/wireframes/...`) in public-facing links
- **Don't** use the same GRAD constant for the logo, heading emphasis, button, and stat values — it flattens every surface to the same visual weight
- **Don't** ship the employee portal without a mobile sidebar breakpoint — employees are mobile-first
