import React, { useState, useRef } from 'react';
import {
  View, Text, ScrollView, Pressable, StyleSheet, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

const CONSENT_VERSION = '2025-06-01';

// ── Consent items ─────────────────────────────────────────────────
const SECTIONS = [
  {
    id: 'what',
    icon: '📄',
    title: 'What PRANA processes',
    items: [
      'Documents pushed by your employer (salary slips, Form 16, letters)',
      'Documents you upload yourself',
      'Career events inferred from your documents',
    ],
  },
  {
    id: 'how',
    icon: '🔒',
    title: 'How your data is handled',
    items: [
      'Documents are processed in-memory by an LLM — raw figures are never stored',
      'Only insights and growth indices are stored, not salary numbers or PAN',
      'Your PAN is encrypted immediately at ingestion — never stored in plaintext',
      'Password-protected documents are decrypted only in a time-limited session you control',
    ],
  },
  {
    id: 'who',
    icon: '👥',
    title: 'Who can see your documents',
    items: [
      'Only you, by default',
      'Third parties only via time-limited share links you create',
      'PRANA staff cannot access your document content — only encrypted metadata',
    ],
  },
  {
    id: 'rights',
    icon: '⚖️',
    title: 'Your rights under DPDP Act 2023',
    items: [
      'Right to access — download all your data at any time',
      'Right to correction — dispute any wrongly attributed document',
      'Right to erasure — request full account and data deletion',
      'Right to withdraw consent — you may withdraw at any time',
    ],
  },
];

// ── Accordion item ────────────────────────────────────────────────
function ConsentSection({
  section, expanded, onToggle,
}: {
  section: typeof SECTIONS[0];
  expanded: boolean;
  onToggle: () => void;
}) {
  const anim = useRef(new Animated.Value(expanded ? 1 : 0)).current;

  React.useEffect(() => {
    Animated.timing(anim, {
      toValue: expanded ? 1 : 0,
      duration: 220,
      useNativeDriver: false,
    }).start();
  }, [expanded]);

  return (
    <View style={styles.section}>
      <Pressable style={styles.sectionHeader} onPress={onToggle}>
        <View style={styles.sectionIconWrap}>
          <Text style={styles.sectionIcon}>{section.icon}</Text>
        </View>
        <Text style={styles.sectionTitle}>{section.title}</Text>
        <Text style={[styles.chevron, expanded && styles.chevronOpen]}>›</Text>
      </Pressable>

      <Animated.View style={{
        maxHeight: anim.interpolate({ inputRange: [0, 1], outputRange: [0, 300] }),
        overflow: 'hidden',
        opacity: anim,
      }}>
        <View style={styles.sectionBody}>
          {section.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <View style={styles.bullet} />
              <Text style={styles.itemText}>{item}</Text>
            </View>
          ))}
        </View>
      </Animated.View>
    </View>
  );
}

// ── Screen ────────────────────────────────────────────────────────
export default function ConsentScreen() {
  const [expanded, setExpanded] = useState<string>('what');
  const [agreed,   setAgreed]   = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  function toggle(id: string) {
    setExpanded(prev => prev === id ? '' : id);
  }

  async function handleAccept() {
    if (!agreed || loading) return;
    setError('');
    setLoading(true);
    try {
      const stepToken = authStore.getStepToken();
      await api.post('/auth/employee/consent', {
        step_token:       stepToken,
        consent_version:  CONSENT_VERSION,
        consented_at:     new Date().toISOString(),
      });
      router.replace('/(vault)/vault');
    } catch {
      setError('Couldn\'t record consent. Check your connection and try again.');
      setLoading(false);
    }
  }

  return (
    <LinearGradient
      colors={['#1E2A4F', colors.space2, colors.space]}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={styles.screen}
    >
      <View style={styles.orb1} pointerEvents="none" />
      <View style={styles.orb2} pointerEvents="none" />

      <SafeAreaView style={styles.safe}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Brand */}
          <View style={styles.brand}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.brandMark}>
              <Text style={styles.brandIcon}>P</Text>
            </LinearGradient>
            <Text style={styles.brandName}>PRANA</Text>
          </View>

          {/* Heading */}
          <Text style={styles.heading}>Before we begin</Text>
          <Text style={styles.sub}>
            Under India's DPDP Act 2023, we need your informed consent before processing any of your documents. Please read what we do — and what we don't.
          </Text>

          {/* DPDP badge */}
          <View style={styles.dpdpBadge}>
            <Text style={styles.dpdpText}>⚖️  Compliant with Digital Personal Data Protection Act 2023</Text>
          </View>

          {/* Accordion sections */}
          <View style={styles.accordion}>
            {SECTIONS.map(s => (
              <ConsentSection
                key={s.id}
                section={s}
                expanded={expanded === s.id}
                onToggle={() => toggle(s.id)}
              />
            ))}
          </View>

          {/* Agreement checkbox */}
          <Pressable style={styles.checkRow} onPress={() => setAgreed(v => !v)}>
            <View style={[styles.checkbox, agreed && styles.checkboxChecked]}>
              {agreed && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <Text style={styles.checkLabel}>
              I have read and understood how PRANA processes my data. I consent to the processing described above.
            </Text>
          </Pressable>

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {/* CTA */}
          <Pressable onPress={handleAccept} disabled={!agreed || loading} style={styles.btnWrap}>
            <LinearGradient
              colors={gradJourney.colors}
              locations={gradJourney.locations}
              start={gradJourney.start}
              end={gradJourney.end}
              style={[styles.btnGrad, (!agreed || loading) && styles.btnDim]}
            >
              <Text style={styles.btnText}>
                {loading ? 'Recording consent…' : 'I consent — Open my vault →'}
              </Text>
            </LinearGradient>
          </Pressable>

          <View style={styles.footerNote}>
            <Text style={styles.footerText}>
              You can withdraw consent or request data deletion at any time from Settings → My Data Rights.
            </Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  orb1: {
    position: 'absolute', width: 200, height: 200, borderRadius: 100,
    backgroundColor: colors.indigo, opacity: 0.16, top: -60, right: -60,
  },
  orb2: {
    position: 'absolute', width: 160, height: 160, borderRadius: 80,
    backgroundColor: colors.emerald, opacity: 0.09, bottom: 80, left: -60,
  },
  safe: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { padding: 24, paddingBottom: 40 },

  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 28 },
  brandMark: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 18, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 18, color: '#FFFFFF', letterSpacing: -0.1 },

  heading: {
    fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF',
    letterSpacing: -0.3, lineHeight: 32, marginBottom: 8,
  },
  sub: { fontSize: 13, color: '#9CA8C9', lineHeight: 20, marginBottom: 16 },

  dpdpBadge: {
    backgroundColor: 'rgba(99,102,241,0.12)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.25)',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
    marginBottom: 24,
  },
  dpdpText: { fontFamily: fonts.mono, fontSize: 11, color: colors.indigo, textAlign: 'center' },

  accordion: {
    borderRadius: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)',
    overflow: 'hidden',
    marginBottom: 24,
  },

  section: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  sectionHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 16, backgroundColor: 'rgba(255,255,255,0.04)',
  },
  sectionIconWrap: {
    width: 34, height: 34, borderRadius: 10,
    backgroundColor: 'rgba(255,255,255,0.06)',
    alignItems: 'center', justifyContent: 'center',
  },
  sectionIcon: { fontSize: 16 },
  sectionTitle: {
    flex: 1, fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#E2E8F0',
  },
  chevron: {
    fontSize: 20, color: '#5C6685',
    transform: [{ rotate: '0deg' }],
  },
  chevronOpen: { transform: [{ rotate: '90deg' }] },

  sectionBody: { paddingHorizontal: 16, paddingBottom: 16, gap: 10 },
  itemRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  bullet: {
    width: 5, height: 5, borderRadius: 3,
    backgroundColor: colors.emerald, marginTop: 6, flexShrink: 0,
  },
  itemText: { flex: 1, fontSize: 12, color: '#9CA8C9', lineHeight: 19 },

  checkRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 16, padding: 14, marginBottom: 16,
  },
  checkbox: {
    width: 22, height: 22, borderRadius: 7,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1,
  },
  checkboxChecked: {
    backgroundColor: colors.emerald, borderColor: colors.emerald,
  },
  checkmark: { fontSize: 12, color: '#04261C', fontWeight: '700' },
  checkLabel: { flex: 1, fontSize: 12, color: '#CBD5E1', lineHeight: 19 },

  btnWrap: { marginBottom: 16 },
  btnGrad: { borderRadius: 16 },
  btnDim: { opacity: 0.35 },
  btnText: {
    fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C',
    textAlign: 'center', padding: 16,
  },

  errorBox: {
    backgroundColor: 'rgba(251,113,133,0.10)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 12,
  },
  errorText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5', textAlign: 'center' },

  footerNote: {
    borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.07)',
    paddingTop: 16,
  },
  footerText: { fontSize: 11, color: '#5C6685', lineHeight: 17, textAlign: 'center' },
});
