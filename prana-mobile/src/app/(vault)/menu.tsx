import React from 'react';
import { View, Text, Pressable, StyleSheet, Modal } from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney, radius } from '@/prana-theme/tokens';

const MENU_ITEMS = [
  { icon: '🗂', label: 'My Vault',      sub: 'Documents & history',      onPress: () => router.push('/(vault)/vault') },
  { icon: '💼', label: 'Career',         sub: 'Employers & timeline',      onPress: () => router.push('/(vault)/career') },
  { icon: '❤️', label: 'Vault Health',   sub: 'Completeness & gaps',       onPress: () => router.push('/(vault)/vault-health' as any) },
  { icon: '📩', label: 'Doc Requests',   sub: 'Request missing documents',  onPress: () => router.push('/(vault)/doc-request' as any) },
  { icon: '↗', label: 'Shares',         sub: 'Active share links',         onPress: () => router.push('/(vault)/shares') },
  { icon: '🔍', label: 'Privacy',        sub: 'Access log & grievances',    onPress: () => router.push('/(vault)/privacy' as any) },
  { icon: '⚙', label: 'Settings',       sub: 'Account & devices',          onPress: () => router.push('/(vault)/settings') },
];

export default function MenuModal() {
  const { signOut, profile } = useAuth();

  return (
    <View style={styles.overlay}>
      <Pressable style={styles.backdrop} onPress={() => router.back()} />
      <View style={styles.panel}>
        {/* Profile — tappable, opens profile screen */}
        <Pressable
          style={styles.profile}
          onPress={() => { router.push('/(vault)/profile' as any); router.back(); }}
        >
          <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.avatar}>
            <Text style={styles.avatarText}>{profile?.name?.charAt(0) ?? '?'}</Text>
          </LinearGradient>
          <View style={{ flex: 1 }}>
            <Text style={styles.profileName}>{profile?.name ?? '—'}</Text>
            <Text style={styles.profileUrl}>
              {profile?.active_since
                ? `Active since ${new Date(profile.active_since).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })} · ${profile.employer_count} employers`
                : 'Loading…'}
            </Text>
          </View>
          <Text style={{ fontSize: 18, color: 'rgba(139,147,167,0.7)', marginRight: 4 }}>›</Text>
        </Pressable>

        <View style={styles.divider} />

        {MENU_ITEMS.map((item) => (
          <Pressable key={item.label} style={styles.item} onPress={() => { item.onPress(); router.back(); }}>
            <View style={styles.itemIcon}><Text style={{ fontSize: 15 }}>{item.icon}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.itemLabel}>{item.label}</Text>
              <Text style={styles.itemSub}>{item.sub}</Text>
            </View>
          </Pressable>
        ))}

        <View style={styles.divider} />

        <Pressable style={[styles.item, styles.itemDanger]} onPress={() => { signOut(); router.replace('/(auth)/sign-in'); }}>
          <View style={[styles.itemIcon, { backgroundColor: 'rgba(251,113,133,0.15)' }]}>
            <Text style={{ fontSize: 15 }}>🚪</Text>
          </View>
          <Text style={styles.dangerLabel}>Sign out</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(10,14,28,0.55)' },
  backdrop: { flex: 1 },
  panel: {
    marginHorizontal: 12, marginBottom: 20,
    backgroundColor: 'rgba(30,42,79,0.96)',
    borderRadius: 20, padding: 8,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
  },
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, paddingBottom: 14 },
  avatar: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },
  profileName: { fontFamily: fonts.displayBold, fontSize: 15, color: '#FFFFFF' },
  profileUrl: { fontFamily: fonts.mono, fontSize: 11, color: '#8B93A7', marginTop: 1 },
  divider: { height: 1, backgroundColor: 'rgba(255,255,255,0.08)', marginHorizontal: 8, marginVertical: 4 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10, borderRadius: 12 },
  itemIcon: { width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.06)', alignItems: 'center', justifyContent: 'center' },
  itemLabel: { fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#E2E8F0' },
  itemSub: { fontSize: 11, color: '#8B93A7', marginTop: 1 },
  itemDanger: {},
  dangerLabel: { fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#FCA5A5' },
});
