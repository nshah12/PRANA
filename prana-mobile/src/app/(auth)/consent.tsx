import React, { useState, useRef } from 'react';
import {
  View, Text, ScrollView, Pressable, StyleSheet, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { tError, tConsent } from '@/i18n';

const CONSENT_VERSION = '2025-06-01';

type ConsentSectionData = { id: string; icon: string; title: string; items: string[] }

function getConsentSections(): ConsentSectionData[] {
  return [
    {
      id: 'what',
      icon: '📄',
      title: tConsent('SECT_WHAT_TITLE'),
      items: [
        tConsent('SECT_WHAT_ITEM1'),
        tConsent('SECT_WHAT_ITEM2'),
        tConsent('SECT_WHAT_ITEM3'),
      ],
    },
    {
      id: 'how',
      icon: '🔒',
      title: tConsent('SECT_HOW_TITLE'),
      items: [
        tConsent('SECT_HOW_ITEM1'),
        tConsent('SECT_HOW_ITEM2'),
        tConsent('SECT_HOW_ITEM3'),
        tConsent('SECT_HOW_ITEM4'),
      ],
    },
    {
      id: 'who',
      icon: '👥',
      title: tConsent('SECT_WHO_TITLE'),
      items: [
        tConsent('SECT_WHO_ITEM1'),
        tConsent('SECT_WHO_ITEM2'),
        tConsent('SECT_WHO_ITEM3'),
      ],
    },
    {
      id: 'rights',
      icon: '⚖️',
      title: tConsent('SECT_RIGHTS_TITLE'),
      items: [
        tConsent('SECT_RIGHTS_ITEM1'),
        tConsent('SECT_RIGHTS_ITEM2'),
        tConsent('SECT_RIGHTS_ITEM3'),
        tConsent('SECT_RIGHTS_ITEM4'),
      ],
    },
  ]
}

// ── Accordion item ────────────────────────────────────────────────
function ConsentSection({
  section, expanded, onToggle,
}: {
  section: ConsentSectionData;
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
  const { signIn } = useAuth();
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
      // Final setup step — the backend issues the access token here (consent is the
      // last gate before the vault opens), so it must be stored via signIn() before
      // navigating, same as the TOTP/biometric verify flows.
      const res = await api.post<{ access_token: string }>('/auth/employee/setup/consent', {
        step_token:       stepToken,
        consent_version:  CONSENT_VERSION,
        consented_at:     new Date().toISOString(),
      });
      signIn(res.access_token);
      router.replace('/(vault)/vault');
    } catch {
      setError(tError('CONSENT_RECORD_FAILED'));
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
          <Text style={styles.heading}>{tConsent('HEADING')}</Text>
          <Text style={styles.sub}>{tConsent('SUB')}</Text>

          {/* DPDP badge */}
          <View style={styles.dpdpBadge}>
            <Text style={styles.dpdpText}>{tConsent('DPDP_BADGE')}</Text>
          </View>

          {/* Accordion sections */}
          <View style={styles.accordion}>
            {getConsentSections().map(s => (
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
              {tConsent('CHECKBOX_LABEL')}
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
                {loading ? tConsent('BTN_LOADING') : tConsent('BTN_ACCEPT')}
              </Text>
            </LinearGradient>
          </Pressable>

          <View style={styles.footerNote}>
            <Text style={styles.footerText}>
              {tConsent('FOOTER_NOTE')}
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
