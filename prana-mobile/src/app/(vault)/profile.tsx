import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney, radius } from '@/prana-theme/tokens';

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={[styles.infoValue, mono && styles.infoValueMono]}>{value}</Text>
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionCard}>{children}</View>
    </View>
  );
}

export default function ProfileScreen() {
  const { profile, signOut } = useAuth();

  function handleSignOut() {
    signOut();
    router.replace('/(auth)/sign-in');
  }

  if (!profile) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={colors.indigo} />
        </View>
      </SafeAreaView>
    );
  }

  // Mask mobile: show last 4 digits — e.g. +91 ●●●● ●●●● 7823
  const mobile = profile.mobile ?? '';
  const maskedMobile = mobile.length >= 4
    ? `+91 ●●●● ●●●● ${mobile.slice(-4)}`
    : mobile;

  const activeSince = profile.active_since
    ? new Date(profile.active_since).toLocaleDateString('en-IN', {
        day: 'numeric', month: 'long', year: 'numeric',
      })
    : '—';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Text style={styles.backChev}>‹</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Profile</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Avatar + name card */}
        <View style={styles.heroCard}>
          <LinearGradient
            colors={gradJourney.colors}
            locations={gradJourney.locations}
            start={gradJourney.start}
            end={gradJourney.end}
            style={styles.avatar}
          >
            <Text style={styles.avatarText}>{profile.name?.charAt(0) ?? '?'}</Text>
          </LinearGradient>
          <Text style={styles.heroName}>{profile.name}</Text>
          <Text style={styles.heroSub}>PRANA Vault Member</Text>

          {/* Stat chips */}
          <View style={styles.statRow}>
            <View style={styles.statChip}>
              <Text style={styles.statNum}>{profile.employer_count ?? 0}</Text>
              <Text style={styles.statLabel}>Employers</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statChip}>
              <Text style={styles.statNum}>
                {profile.active_since
                  ? `${new Date().getFullYear() - new Date(profile.active_since).getFullYear()}y`
                  : '—'}
              </Text>
              <Text style={styles.statLabel}>On PRANA</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statChip}>
              <Text style={[styles.statNum, { fontSize: 13 }]}>Active</Text>
              <Text style={styles.statLabel}>Status</Text>
            </View>
          </View>
        </View>

        {/* Vault link */}
        <Section title="Vault">
          <InfoRow label="Vault URL" value={profile.vault_url ?? '—'} mono />
          <InfoRow label="Member since" value={activeSince} />
        </Section>

        {/* Contact */}
        <Section title="Contact">
          <InfoRow label="Mobile" value={maskedMobile} mono />
        </Section>

        {/* Security */}
        <Section title="Security">
          <InfoRow label="TOTP 2FA" value={profile.has_totp ? 'Enabled ✓' : 'Not set up'} />
          <Pressable
            style={styles.linkRow}
            onPress={() => router.push('/(vault)/settings')}
          >
            <Text style={styles.linkText}>Manage devices & biometrics</Text>
            <Text style={styles.linkChev}>›</Text>
          </Pressable>
        </Section>

        {/* Data rights */}
        <Section title="Privacy & Data">
          <Pressable
            style={styles.linkRow}
            onPress={() => router.push('/(vault)/data-rights')}
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.linkText}>My Data Rights</Text>
              <Text style={styles.linkSub}>DPDP Act 2023 · Consent, export, erasure</Text>
            </View>
            <Text style={styles.linkChev}>›</Text>
          </Pressable>
        </Section>

        {/* Sign out */}
        <Pressable style={styles.signOutBtn} onPress={handleSignOut}>
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>

        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  // Header
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12,
  },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  backChev: { fontSize: 26, color: colors.ink, lineHeight: 30, fontFamily: fonts.bodyRegular },
  headerTitle: { fontSize: 17, fontFamily: fonts.displayBold, color: colors.ink },

  scroll: { paddingHorizontal: 16, paddingTop: 8 },

  // Hero card
  heroCard: {
    backgroundColor: colors.surface3,
    borderRadius: 24,
    alignItems: 'center',
    paddingVertical: 28,
    paddingHorizontal: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
  },
  avatar: {
    width: 80, height: 80, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 14,
  },
  avatarText: { fontFamily: fonts.displayBold, fontSize: 32, color: '#04261C' },
  heroName: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.ink, marginBottom: 4 },
  heroSub: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3, marginBottom: 20 },

  statRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 14, paddingHorizontal: 8, paddingVertical: 12,
    alignSelf: 'stretch',
  },
  statChip: { flex: 1, alignItems: 'center' },
  statNum: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink },
  statLabel: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  statDivider: { width: 1, height: 28, backgroundColor: 'rgba(255,255,255,0.08)' },

  // Sections
  section: { marginBottom: 16 },
  sectionTitle: {
    fontFamily: fonts.mono, fontSize: 11, color: colors.ink3,
    textTransform: 'uppercase', letterSpacing: 0.8,
    marginBottom: 6, marginLeft: 4,
  },
  sectionCard: {
    backgroundColor: colors.surface3,
    borderRadius: 18,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
  },

  // Info rows
  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 13,
    borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)',
  },
  infoLabel: { fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink3 },
  infoValue: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  infoValueMono: { fontFamily: fonts.mono, fontSize: 12 },

  // Link rows (chevron)
  linkRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 13,
  },
  linkText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, flex: 1 },
  linkSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  linkChev: { fontSize: 20, color: colors.ink3 },

  // Sign out
  signOutBtn: {
    marginTop: 8, paddingVertical: 15, borderRadius: 18,
    backgroundColor: 'rgba(251,113,133,0.10)',
    borderWidth: 1, borderColor: 'rgba(251,113,133,0.25)',
    alignItems: 'center',
  },
  signOutText: { fontFamily: fonts.bodySemiBold, fontSize: 15, color: '#FB7185' },
});
