import React from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

interface AuthScreenProps {
  children: React.ReactNode;
  scrollable?: boolean;
}

export function AuthScreen({ children, scrollable = true }: AuthScreenProps) {
  const content = scrollable ? (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.scrollContent}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  ) : (
    <View style={styles.scrollContent}>{children}</View>
  );

  return (
    <LinearGradient
      colors={['#1E2A4F', colors.space2, colors.space]}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={styles.screen}
    >
      {/* Indigo orb top-right */}
      <View style={styles.orb1} pointerEvents="none" />
      {/* Emerald orb bottom-left */}
      <View style={styles.orb2} pointerEvents="none" />
      <SafeAreaView style={styles.safe}>
        {content}
      </SafeAreaView>
    </LinearGradient>
  );
}

export function AuthBrand() {
  return (
    <View style={styles.brand}>
      <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.brandMark}>
        <Text style={styles.brandIcon}>P</Text>
      </LinearGradient>
      <Text style={styles.brandName}>PRANA</Text>
    </View>
  );
}

export function AuthHeading({ title, sub }: { title: string; sub?: string }) {
  return (
    <View style={styles.headingBlock}>
      <Text style={styles.heading}>{title}</Text>
      {sub ? <Text style={styles.sub}>{sub}</Text> : null}
    </View>
  );
}

export function GlassCard({ children }: { children: React.ReactNode }) {
  return <View style={styles.glassCard}>{children}</View>;
}

export function GlassField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.glassField}>
      <Text style={styles.glassLabel}>{label}</Text>
      {children}
    </View>
  );
}

export function BtnGrad({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.btnGrad}>
      <Text style={styles.btnGradText} onPress={onPress}>{label}</Text>
    </LinearGradient>
  );
}

export function BtnGhost({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <View style={styles.btnGhost}>
      <Text style={styles.btnGhostText} onPress={onPress}>{label}</Text>
    </View>
  );
}

export function InfoPill({ text }: { text: string }) {
  return (
    <View style={styles.infoPill}>
      <Text style={styles.infoPillIcon}>ℹ</Text>
      <Text style={styles.infoPillText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  orb1: {
    position: 'absolute', width: 200, height: 200, borderRadius: 100,
    backgroundColor: colors.indigo, opacity: 0.18, top: -60, right: -60,
  },
  orb2: {
    position: 'absolute', width: 160, height: 160, borderRadius: 80,
    backgroundColor: colors.emerald, opacity: 0.1, bottom: 80, left: -60,
  },
  safe: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { flexGrow: 1, padding: 24 },

  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 32 },
  brandMark: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 18, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 18, color: '#FFFFFF', letterSpacing: -0.1 },

  headingBlock: { marginBottom: 28 },
  heading: { fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF', letterSpacing: -0.3, lineHeight: 32, marginBottom: 6 },
  sub: { fontSize: 13, color: '#9CA8C9', lineHeight: 20 },

  glassCard: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 20, padding: 16, marginBottom: 12,
  },
  glassField: { marginBottom: 14 },
  glassLabel: {
    fontFamily: fonts.mono, fontSize: 11, color: '#8B93A7',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6,
  },

  btnGrad: { borderRadius: 16, marginBottom: 10 },
  btnGradText: {
    fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C',
    textAlign: 'center', padding: 16,
  },
  btnGhost: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 16, marginBottom: 10,
  },
  btnGhostText: {
    fontFamily: fonts.bodySemiBold, fontSize: 14, color: '#CBD5E1',
    textAlign: 'center', padding: 14,
  },

  infoPill: {
    flexDirection: 'row', gap: 8, alignItems: 'flex-start',
    backgroundColor: 'rgba(99,102,241,0.10)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.20)',
    borderRadius: 14, padding: 12, marginTop: 12,
  },
  infoPillIcon: { fontSize: 14, color: colors.indigo, marginTop: 1 },
  infoPillText: { flex: 1, fontSize: 12, color: '#9CA8C9', lineHeight: 18 },
});
