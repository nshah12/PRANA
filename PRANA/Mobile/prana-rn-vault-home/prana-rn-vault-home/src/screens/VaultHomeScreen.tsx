// src/screens/VaultHomeScreen.tsx
//
// Translation of SCREEN 9 ("Vault home — hero + stats + docs") from
// PRANA_Mobile_App_Prototype.html into React Native (Expo).
//
// ── Translation notes (things that DON'T map 1:1 from CSS) ──────────────
//
// 1. .vault-topbg used `radial-gradient(... at 50% -20% ...)`. expo-linear-
//    gradient only supports linear gradients, so this is approximated with
//    a vertical LinearGradient (gradTopBg in tokens.ts). The `.auth-orb`
//    blurred circle in the corner does most of the visual "glow" work and
//    translates fine via a semi-transparent View + a blur-like effect
//    (RN has no CSS `filter: blur()` on Views -- see AuthOrb below).
//
// 2. .vault-hero-label used `color: rgba(4,38,28,.65)` directly on top of
//    the gradient background -- this works identically in RN since it's
//    just a Text color over a LinearGradient View. No gradient-TEXT was
//    needed on this screen (unlike the splash/sign-in screens, which use
//    `background-clip: text` -- that DOES need react-native-masked-view
//    and is a bigger lift, not needed here).
//
// 3. `position: absolute` + `margin: -1.6rem ...` (the hero card overlapping
//    the dark header) translates directly -- RN supports negative margins
//    and absolute positioning the same way.
//
// 4. The bottom nav's `backdrop-filter: blur(20px)` -> expo-blur's
//    <BlurView> (see VaultNav.tsx). This is a different mechanism (real-time
//    blur of background content vs. a CSS filter) but the visual result is
//    close. Android blur support is inconsistent below API 31, hence the
//    solid-color fallback in VaultNav.
//
// 5. Emoji icons (🔔 💰 🧾 📊 🛡 ⬆) are used as-is -- RN renders emoji via
//    the system font same as any Text node, no extra library needed. For a
//    production app these would likely become SVG icon components
//    (react-native-svg) for consistent cross-platform rendering, but emoji
//    is a reasonable "looks right on both iOS and Android" placeholder, same
//    as the HTML prototype.
//
// 6. Scrolling: .vault-body had `overflow-y: auto` with extra bottom padding
//    to clear the floating nav + FAB. In RN this is a <ScrollView> with
//    contentContainerStyle paddingBottom -- same idea.

import React from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, StatusBar } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts, radius, gradJourney, gradTopBg } from '../theme/tokens';
import { StatCard } from '../components/StatCard';
import { DocumentCard } from '../components/DocumentCard';
import { VaultNav } from '../components/VaultNav';

export function VaultHomeScreen() {
  return (
    <View style={styles.screen}>
      {/* ── Dark header: .vault-topbg + .auth-orb + .vault-status + .vault-greeting ── */}
      <LinearGradient
        colors={gradTopBg.colors}
        locations={gradTopBg.locations}
        start={gradTopBg.start}
        end={gradTopBg.end}
        style={styles.topBg}
      >
        {/* .auth-orb.o1 -- blurred indigo glow, top-right.
            RN has no `filter: blur()`, so we fake the blur by using a large
            soft-edged circle at low opacity. A true blur would need
            expo-blur's BlurView positioned absolutely, or a pre-rendered
            blurred PNG asset -- the opacity+size approach below is the
            cheapest reasonable approximation for a static glow. */}
        <View style={styles.orb} pointerEvents="none" />

        <SafeAreaView edges={['top']}>
          <View style={styles.statusRow}>
            <Text style={styles.statusTime}>9:43</Text>
            <Text style={styles.statusDots}>●●●</Text>
          </View>

          <View style={styles.greetingRow}>
            <View>
              <Text style={styles.hi}>Good morning</Text>
              <Text style={styles.name}>Rahul Sharma</Text>
            </View>
            <Pressable style={styles.bell}>
              <Text style={styles.bellIcon}>🔔</Text>
              <View style={styles.bellDot} />
            </Pressable>
          </View>
        </SafeAreaView>
      </LinearGradient>

      {/* ── Hero card: .vault-hero (gradient, overlaps header via negative margin) ── */}
      <LinearGradient
        colors={gradJourney.colors}
        locations={gradJourney.locations}
        start={gradJourney.start}
        end={gradJourney.end}
        style={styles.hero}
      >
        <Text style={styles.heroLabel}>YOUR PERMANENT VAULT</Text>
        <Text style={styles.heroUrl} numberOfLines={1}>
          prana.in/vault/rahul-sharma-xk72
        </Text>
        <Text style={styles.heroMeta}>Active since Mar 2019 · 2 employers · 16 documents</Text>
      </LinearGradient>

      {/* ── Body: .vault-body (scrollable, stats + document list) ── */}
      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.bodyContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.statGrid}>
          <StatCard value={16} label="Documents" accent="indigo" />
          <StatCard value={3} label="Active shares" accent="emerald" />
        </View>

        <Text style={styles.sectionLabel}>RECENT DOCUMENTS</Text>

        <DocumentCard
          iconType="salary"
          iconEmoji="💰"
          title="Salary Slip — May 2026"
          meta="NPCI · Pushed by employer"
          calMonth="JUN"
          calDay="02"
          dateLabel="Received"
          provenance="employer"
        />

        <DocumentCard
          iconType="form16"
          iconEmoji="🧾"
          title="Form 16 — FY 2024-25"
          meta="NPCI · Pushed by employer"
          calMonth="MAY"
          calDay="28"
          dateLabel="Received"
          provenance="employer"
        />

        <DocumentCard
          iconType="invest"
          iconEmoji="📊"
          title="Investment Proof — LIC"
          meta="Self-uploaded"
          calMonth="JUN"
          calDay="12"
          dateLabel="Uploaded"
          provenance="self"
        />
      </ScrollView>

      {/* ── FAB: .vault-fab (gradient, absolute bottom-right) ── */}
      <Pressable style={styles.fabWrapper}>
        <LinearGradient
          colors={gradJourney.colors}
          locations={gradJourney.locations}
          start={gradJourney.start}
          end={gradJourney.end}
          style={styles.fab}
        >
          <Text style={styles.fabIcon}>⬆</Text>
        </LinearGradient>
      </Pressable>

      {/* ── Floating bottom nav ── */}
      <VaultNav active="vault" onPress={() => {}} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.surface, // #FAFAF8
  },

  // .vault-topbg
  topBg: {
    paddingHorizontal: 24,
    paddingBottom: 38,
    overflow: 'hidden', // clip the orb to this container's bounds
  },

  // .auth-orb.o1 (approximation -- see comment block above)
  orb: {
    position: 'absolute',
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: colors.indigo,
    opacity: 0.18, // lower than CSS's .35 since we have no blur softening the edge
    top: -60,
    right: -60,
  },

  // .vault-status
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 16,
    paddingBottom: 22,
  },
  statusTime: {
    fontFamily: fonts.mono,
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  statusDots: {
    fontFamily: fonts.mono,
    fontSize: 12,
    color: '#FFFFFF',
  },

  // .vault-greeting
  greetingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  hi: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: '#9CA8C9',
    marginBottom: 2,
  },
  name: {
    fontFamily: fonts.displayBold,
    fontSize: 24,
    color: '#FFFFFF',
    letterSpacing: -0.2,
  },

  // .vault-bell
  bell: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  bellIcon: {
    fontSize: 16,
  },
  bellDot: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.amber,
    borderWidth: 2,
    borderColor: colors.space,
  },

  // .vault-hero (margin: -1.6rem 1.2rem 0 -- negative top margin pulls it
  // up over the dark header by ~26px)
  hero: {
    marginTop: -26,
    marginHorizontal: 19,
    borderRadius: radius.xl, // 22
    padding: 21,
    // box-shadow: 0 16px 40px -12px rgba(99,102,241,.5)
    shadowColor: colors.indigo,
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.5,
    shadowRadius: 28,
    elevation: 10,
    zIndex: 10,
  },
  heroLabel: {
    fontFamily: fonts.mono,
    fontSize: 10,
    fontWeight: '700',
    color: 'rgba(4,38,28,0.65)',
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginBottom: 5,
  },
  heroUrl: {
    fontFamily: fonts.mono,
    fontSize: 12.5,
    fontWeight: '600',
    color: '#04261C',
    marginBottom: 6,
  },
  heroMeta: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    color: 'rgba(4,38,28,0.7)',
  },

  // .vault-body
  body: {
    flex: 1,
  },
  bodyContent: {
    paddingHorizontal: 19,
    paddingTop: 26,
    paddingBottom: 104, // clears the floating nav + FAB
  },

  // .stat-grid
  statGrid: {
    flexDirection: 'row',
    gap: 11,
    marginBottom: 26,
  },

  // .vault-section-label
  sectionLabel: {
    fontFamily: fonts.mono,
    fontSize: 11,
    fontWeight: '700',
    color: colors.ink3,
    letterSpacing: 1.3,
    marginBottom: 11,
  },

  // .vault-fab
  fabWrapper: {
    position: 'absolute',
    bottom: 100,
    right: 20,
  },
  fab: {
    width: 54,
    height: 54,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.indigo,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.6,
    shadowRadius: 18,
    elevation: 8,
  },
  fabIcon: {
    fontSize: 22,
    color: '#04261C',
    fontWeight: '700',
  },
});
