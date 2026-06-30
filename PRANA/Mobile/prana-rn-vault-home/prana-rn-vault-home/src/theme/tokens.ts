// src/theme/tokens.ts
//
// Design tokens ported from PRANA_Mobile_App_Prototype.html (:root CSS variables).
// CSS custom properties -> a plain JS object; React Native has no concept of
// CSS variables, so every screen imports from here directly.

export const colors = {
  // Dark "space" surfaces (auth/onboarding screens)
  space: '#0B0F1E',
  space2: '#131B33',
  space3: '#1C2747',

  // Signature accent colors (used individually and as gradient stops)
  indigo: '#6366F1',
  cyan: '#22D3EE',
  emerald: '#34D399',
  amber: '#FBBF24',
  rose: '#FB7185',

  // Light surfaces (vault/data screens)
  surface: '#FAFAF8',
  surface2: '#FFFFFF',
  surface3: '#F0EFEA', // the "light gray" document card background

  // Ink (text) scale
  ink: '#14171F',
  ink2: '#5C6270',
  ink3: '#9CA1AE',
} as const;

// CSS: --grad-journey: linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)
//
// expo-linear-gradient doesn't take an angle directly -- it takes start/end
// points as {x,y} in a 0-1 unit square. 135deg (top-left -> bottom-right-ish,
// CSS measures clockwise from "up") maps approximately to:
//   start: top-left, end: bottom-right
export const gradJourney = {
  colors: [colors.indigo, colors.cyan, colors.emerald] as const,
  locations: [0, 0.55, 1] as const,
  start: { x: 0, y: 0 },
  end: { x: 1, y: 1 },
};

// CSS: .vault-topbg background: radial-gradient(ellipse 140% 100% at 50% -20%, #2A3A6B 0%, var(--space2) 55%, var(--space) 100%)
//
// expo-linear-gradient has no radial mode. We approximate the same visual
// effect (lighter glow at top, fading to space-black) with a vertical linear
// gradient -- close enough at the size of a phone header; the "auth-orb"
// blur circle (see VaultHomeScreen) does most of the work of the glow anyway.
export const gradTopBg = {
  colors: ['#2A3A6B', colors.space2, colors.space] as const,
  locations: [0, 0.55, 1] as const,
  start: { x: 0.5, y: 0 },
  end: { x: 0.5, y: 1 },
};

// Per-document-type icon gradients (.doc-icon.salary / .form16 / .invest)
export const docIconGradients = {
  salary: { colors: ['#6366F1', '#818CF8'] as const, start: { x: 0, y: 0 }, end: { x: 1, y: 1 } },
  form16: { colors: ['#22D3EE', '#34D399'] as const, start: { x: 0, y: 0 }, end: { x: 1, y: 1 } },
  invest: { colors: ['#FBBF24', '#FB923C'] as const, start: { x: 0, y: 0 }, end: { x: 1, y: 1 } },
} as const;

export const fonts = {
  // CSS: --display: 'Space Grotesk' / --body: 'Inter' / --mono: 'DM Mono'
  //
  // These must be loaded via expo-font / @expo-google-fonts before use --
  // see App.tsx. The family names below are the keys expo-font registers
  // them under (by convention, "<Family>_<weight>").
  displayBold: 'SpaceGrotesk_700Bold',
  displaySemiBold: 'SpaceGrotesk_600SemiBold',
  bodyRegular: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemiBold: 'Inter_600SemiBold',
  bodyBold: 'Inter_700Bold',
  mono: 'DMMono_500Medium',
};

export const radius = {
  sm: 10,
  md: 14,
  lg: 18,
  xl: 22,
  pill: 999,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
};
