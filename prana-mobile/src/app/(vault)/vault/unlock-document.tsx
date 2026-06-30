import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet,
  Animated, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { tUi } from '@/i18n';

// ── Session timer ─────────────────────────────────────────────────
const SESSION_SECONDS = 10 * 60; // 10 minutes

function useCountdown(seconds: number, running: boolean) {
  const [remaining, setRemaining] = useState(seconds);
  useEffect(() => {
    if (!running) return;
    if (remaining <= 0) return;
    const t = setInterval(() => setRemaining(r => r - 1), 1000);
    return () => clearInterval(t);
  }, [running, remaining]);
  const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
  const ss = String(remaining % 60).padStart(2, '0');
  return { remaining, display: `${mm}:${ss}` };
}

// ── Processing steps ──────────────────────────────────────────────
const STEPS = [
  'Decrypting document in memory…',
  'Extracting text (no plaintext stored)…',
  'Sending to LLM with PAN redacted…',
  'Storing insights only · Discarding raw data…',
  'Wiping session memory…',
];

// ── Step indicator ────────────────────────────────────────────────
function ProcessingView({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let i = 0;
    const advance = () => {
      if (i >= STEPS.length) { onDone(); return; }
      setStep(i);
      Animated.timing(progress, {
        toValue: (i + 1) / STEPS.length,
        duration: 700,
        useNativeDriver: false,
      }).start();
      i++;
      setTimeout(advance, 900);
    };
    advance();
  }, []);

  const barWidth = progress.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  return (
    <View style={styles.processingWrap}>
      <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.processingOrb}>
        <Text style={{ fontSize: 28 }}>🔐</Text>
      </LinearGradient>
      <Text style={styles.processingTitle}>Processing securely</Text>
      <Text style={styles.processingStep}>{STEPS[step]}</Text>

      <View style={styles.progressTrack}>
        <Animated.View style={[styles.progressBar, { width: barWidth }]} />
      </View>

      <View style={styles.privacyChips}>
        {['In-memory only', 'PAN redacted', 'Raw data discarded'].map(c => (
          <View key={c} style={styles.chip}>
            <Text style={styles.chipText}>{c}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ── Done view ─────────────────────────────────────────────────────
function DoneView({ docTitle, employer }: { docTitle: string; employer: string }) {
  const scale = useRef(new Animated.Value(0.7)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(scale, { toValue: 1, useNativeDriver: true, tension: 120, friction: 7 }),
      Animated.timing(opacity, { toValue: 1, duration: 300, useNativeDriver: true }),
    ]).start();
  }, []);

  return (
    <Animated.View style={[styles.doneWrap, { opacity, transform: [{ scale }] }]}>
      <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.doneOrb}>
        <Text style={{ fontSize: 32 }}>✓</Text>
      </LinearGradient>
      <Text style={styles.doneTitle}>Processed &amp; Routed</Text>
      <Text style={styles.doneSub}>
        <Text style={{ color: '#E2E8F0' }}>{docTitle}</Text>
        {'\n'}from {employer} is now in your vault.
      </Text>

      <View style={styles.doneCard}>
        {[
          ['Decrypted in-memory', '✓'],
          ['PAN redacted before LLM', '✓'],
          ['Raw salary data stored', '✗ Never'],
          ['Insights stored', '✓'],
          ['Session memory wiped', '✓'],
        ].map(([label, val]) => (
          <View key={label} style={styles.doneRow}>
            <Text style={styles.doneLabel}>{label}</Text>
            <Text style={[styles.doneVal, val === '✗ Never' && { color: colors.rose }]}>{val}</Text>
          </View>
        ))}
      </View>

      <Pressable onPress={() => router.back()} style={styles.doneBtnWrap}>
        <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.doneBtn}>
          <Text style={styles.doneBtnText}>Open in vault →</Text>
        </LinearGradient>
      </Pressable>
    </Animated.View>
  );
}

// ── Screen ────────────────────────────────────────────────────────
type Phase = 'enter' | 'processing' | 'done' | 'expired';

export default function UnlockDocumentScreen() {
  const params = useLocalSearchParams<{ docTitle?: string; employer?: string; hint?: string }>();
  const docTitle = params.docTitle ?? 'Salary Slip — May 2026';
  const employer = params.employer ?? 'NPCI';
  const hint = params.hint ?? 'Usually your date of birth (DDMMYYYY) or PAN';

  const [phase, setPhase] = useState<Phase>('enter');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');

  const { remaining, display } = useCountdown(SESSION_SECONDS, phase === 'enter');

  // Auto-expire if user doesn't submit in time
  useEffect(() => {
    if (remaining <= 0 && phase === 'enter') setPhase('expired');
  }, [remaining, phase]);

  function handleUnlock() {
    if (!password.trim()) { setError(tUi('UNLOCK_PROMPT')); return; }
    setError('');
    setPhase('processing');
  }

  // ── Expired ──
  if (phase === 'expired') {
    return (
      <LinearGradient colors={['#1E2A4F', colors.space2, colors.space]} locations={[0, 0.5, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.screen}>
        <SafeAreaView style={styles.safe}>
          <View style={styles.expiredWrap}>
            <Text style={{ fontSize: 48, marginBottom: 16 }}>⏱</Text>
            <Text style={styles.expiredTitle}>Session expired</Text>
            <Text style={styles.expiredSub}>
              For your security, the unlock session has expired. Tap below to start a new session.
            </Text>
            <Pressable onPress={() => router.replace('/(vault)/vault/unlock-document')} style={styles.doneBtnWrap}>
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.doneBtn}>
                <Text style={styles.doneBtnText}>Start new session →</Text>
              </LinearGradient>
            </Pressable>
            <Pressable onPress={() => router.back()}>
              <Text style={styles.cancelLink}>Cancel</Text>
            </Pressable>
          </View>
        </SafeAreaView>
      </LinearGradient>
    );
  }

  // ── Done ──
  if (phase === 'done') {
    return (
      <LinearGradient colors={['#1E2A4F', colors.space2, colors.space]} locations={[0, 0.5, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.screen}>
        <SafeAreaView style={styles.safe}>
          <DoneView docTitle={docTitle} employer={employer} />
        </SafeAreaView>
      </LinearGradient>
    );
  }

  // ── Processing ──
  if (phase === 'processing') {
    return (
      <LinearGradient colors={['#1E2A4F', colors.space2, colors.space]} locations={[0, 0.5, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.screen}>
        <SafeAreaView style={styles.safe}>
          <ProcessingView onDone={() => setPhase('done')} />
        </SafeAreaView>
      </LinearGradient>
    );
  }

  // ── Enter password ──
  return (
    <LinearGradient colors={['#1E2A4F', colors.space2, colors.space]} locations={[0, 0.5, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.screen}>
      <View style={styles.orb1} pointerEvents="none" />
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          {/* Header */}
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} style={styles.backBtn}>
              <Text style={styles.backText}>‹</Text>
            </Pressable>

            {/* Session timer */}
            <View style={[styles.timerBadge, remaining < 120 && styles.timerBadgeWarn]}>
              <Text style={[styles.timerText, remaining < 120 && styles.timerTextWarn]}>
                ⏱ {display}
              </Text>
            </View>
          </View>

          <View style={styles.body}>
            {/* Lock icon */}
            <View style={styles.lockWrap}>
              <Text style={{ fontSize: 40 }}>🔐</Text>
            </View>

            {/* Document info */}
            <Text style={styles.docTitle}>{docTitle}</Text>
            <View style={styles.employerBadge}>
              <Text style={styles.employerText}>from {employer}</Text>
            </View>

            <Text style={styles.heading}>Enter document password</Text>
            <Text style={styles.sub}>
              This document is password-protected. Your password is used only to decrypt it in memory — it is never stored.
            </Text>

            {/* Password field */}
            <View style={styles.fieldCard}>
              <Text style={styles.fieldLabel}>DOCUMENT PASSWORD</Text>
              <View style={styles.fieldRow}>
                <TextInput
                  style={styles.passwordInput}
                  placeholder="Enter password"
                  placeholderTextColor="#5C6685"
                  secureTextEntry={!show}
                  value={password}
                  onChangeText={t => { setPassword(t); setError(''); }}
                  autoFocus
                />
                <Pressable onPress={() => setShow(v => !v)} style={styles.eyeBtn}>
                  <Text style={styles.eyeText}>{show ? '🙈' : '👁'}</Text>
                </Pressable>
              </View>
              {hint ? (
                <Text style={styles.hintText}>💡 {hint}</Text>
              ) : null}
              {error ? (
                <Text style={styles.errorText}>{error}</Text>
              ) : null}
            </View>

            {/* Privacy note */}
            <View style={styles.privacyCard}>
              {[
                '🔒 Password used only to decrypt · Never stored',
                '🧠 Document processed in-memory by LLM',
                '🗑 Raw data discarded after processing',
                `⏱ Session expires in ${display}`,
              ].map(line => (
                <Text key={line} style={styles.privacyLine}>{line}</Text>
              ))}
            </View>

            {/* CTA */}
            <Pressable onPress={handleUnlock} style={styles.unlockBtnWrap}>
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.unlockBtn}>
                <Text style={styles.unlockBtnText}>Decrypt &amp; Process →</Text>
              </LinearGradient>
            </Pressable>

            <Pressable onPress={() => router.back()}>
              <Text style={styles.cancelLink}>Skip for now</Text>
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  orb1: {
    position: 'absolute', width: 200, height: 200, borderRadius: 100,
    backgroundColor: colors.indigo, opacity: 0.15, top: -60, right: -60,
  },
  safe: { flex: 1 },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 4,
  },
  backBtn: { padding: 6 },
  backText: { fontSize: 28, color: '#9CA8C9', lineHeight: 32 },

  timerBadge: {
    backgroundColor: 'rgba(99,102,241,0.15)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.3)',
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5,
  },
  timerBadgeWarn: {
    backgroundColor: 'rgba(251,113,133,0.15)',
    borderColor: 'rgba(251,113,133,0.4)',
  },
  timerText: { fontFamily: fonts.mono, fontSize: 12, color: colors.indigo },
  timerTextWarn: { color: colors.rose },

  body: { flex: 1, padding: 24 },

  lockWrap: { alignItems: 'center', marginBottom: 16 },
  docTitle: {
    fontFamily: fonts.displayBold, fontSize: 17, color: '#FFFFFF',
    textAlign: 'center', marginBottom: 8,
  },
  employerBadge: {
    alignSelf: 'center',
    backgroundColor: 'rgba(52,211,153,0.12)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.25)',
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4, marginBottom: 24,
  },
  employerText: { fontFamily: fonts.mono, fontSize: 11, color: colors.emerald },

  heading: {
    fontFamily: fonts.displayBold, fontSize: 20, color: '#FFFFFF',
    letterSpacing: -0.2, marginBottom: 8,
  },
  sub: { fontSize: 12, color: '#9CA8C9', lineHeight: 19, marginBottom: 20 },

  fieldCard: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 18, padding: 16, marginBottom: 16,
  },
  fieldLabel: {
    fontFamily: fonts.mono, fontSize: 10, color: '#8B93A7',
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 10,
  },
  fieldRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  passwordInput: {
    flex: 1, fontFamily: fonts.mono, fontSize: 15,
    color: '#FFFFFF', paddingVertical: 4,
  },
  eyeBtn: { padding: 4 },
  eyeText: { fontSize: 18 },
  hintText: { fontFamily: fonts.bodyRegular, fontSize: 11, color: '#5C6685', marginTop: 10, lineHeight: 17 },
  errorText: { fontFamily: fonts.bodyRegular, fontSize: 11, color: colors.rose, marginTop: 10 },

  privacyCard: {
    backgroundColor: 'rgba(52,211,153,0.07)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.15)',
    borderRadius: 16, padding: 14, gap: 6, marginBottom: 20,
  },
  privacyLine: { fontFamily: fonts.mono, fontSize: 11, color: '#9CA8C9', lineHeight: 18 },

  unlockBtnWrap: { marginBottom: 12 },
  unlockBtn: { borderRadius: 16 },
  unlockBtnText: {
    fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C',
    textAlign: 'center', padding: 16,
  },
  cancelLink: {
    fontFamily: fonts.bodyRegular, fontSize: 13, color: '#5C6685',
    textAlign: 'center', padding: 8,
  },

  // Processing
  processingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  processingOrb: {
    width: 80, height: 80, borderRadius: 24,
    alignItems: 'center', justifyContent: 'center', marginBottom: 24,
  },
  processingTitle: {
    fontFamily: fonts.displayBold, fontSize: 20, color: '#FFFFFF',
    marginBottom: 10, textAlign: 'center',
  },
  processingStep: {
    fontFamily: fonts.mono, fontSize: 12, color: '#9CA8C9',
    textAlign: 'center', marginBottom: 24, lineHeight: 19,
  },
  progressTrack: {
    width: '100%', height: 4, backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: 2, overflow: 'hidden', marginBottom: 24,
  },
  progressBar: {
    height: 4, borderRadius: 2,
    backgroundColor: colors.emerald,
  },
  privacyChips: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: 'center' },
  chip: {
    backgroundColor: 'rgba(52,211,153,0.12)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.25)',
    borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4,
  },
  chipText: { fontFamily: fonts.mono, fontSize: 10, color: colors.emerald },

  // Done
  doneWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28 },
  doneOrb: {
    width: 80, height: 80, borderRadius: 24,
    alignItems: 'center', justifyContent: 'center', marginBottom: 20,
  },
  doneTitle: {
    fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF',
    marginBottom: 10, textAlign: 'center',
  },
  doneSub: {
    fontSize: 13, color: '#9CA8C9', textAlign: 'center',
    lineHeight: 21, marginBottom: 24,
  },
  doneCard: {
    width: '100%',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 18, padding: 16, gap: 10, marginBottom: 24,
  },
  doneRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  doneLabel: { fontFamily: fonts.bodyRegular, fontSize: 12, color: '#9CA8C9' },
  doneVal: { fontFamily: fonts.mono, fontSize: 12, color: colors.emerald, fontWeight: '700' },
  doneBtnWrap: { width: '100%', marginBottom: 12 },
  doneBtn: { borderRadius: 16 },
  doneBtnText: {
    fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C',
    textAlign: 'center', padding: 16,
  },

  // Expired
  expiredWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  expiredTitle: {
    fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF',
    marginBottom: 10, textAlign: 'center',
  },
  expiredSub: {
    fontSize: 13, color: '#9CA8C9', textAlign: 'center',
    lineHeight: 21, marginBottom: 28,
  },
});
