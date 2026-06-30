import React, { useRef, useState, useEffect } from 'react';
import {
  View, Text, TextInput, StyleSheet, Pressable, ActivityIndicator, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { tError, tUi } from '@/i18n';

const CODE_LEN = 6;

export default function TotpVerifyScreen() {
  const { signIn } = useAuth();
  const [code,     setCode]     = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [attempts, setAttempts] = useState(0); // track locally; server enforces lockout
  const inputRef  = useRef<TextInput>(null);
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const fadeIn    = useRef(new Animated.Value(0)).current;
  const successScale = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }).start();
    // Small delay so keyboard doesn't interrupt the fade
    setTimeout(() => inputRef.current?.focus(), 300);
  }, []);

  useEffect(() => {
    if (code.length === CODE_LEN) handleVerify();
  }, [code]);

  function shake() {
    shakeAnim.setValue(0);
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10,  duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 6,   duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0,   duration: 55, useNativeDriver: true }),
    ]).start();
  }

  async function handleVerify() {
    if (code.length !== CODE_LEN || loading) return;
    setError('');
    setLoading(true);
    try {
      const stepToken = authStore.getStepToken();
      if (!stepToken) {
        router.replace('/(auth)/sign-in');
        return;
      }
      const res = await api.post<{ access_token: string; is_new_device: boolean }>(
        '/auth/employee/totp',
        { step_token: stepToken, code },
      );

      // Animate success before navigating
      Animated.spring(successScale, { toValue: 1, friction: 4, tension: 200, useNativeDriver: true }).start();
      await new Promise(r => setTimeout(r, 550));

      signIn(res.access_token);

      if (res.is_new_device) {
        router.replace('/(auth)/register-device');
      } else {
        router.replace('/(vault)/vault');
      }
    } catch (e: any) {
      const errCode = e?.body?.error ?? e?.response?.data?.error;
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);

      if (errCode === 'INVALID_TOTP') {
        const remaining = Math.max(0, 5 - newAttempts);
        if (remaining === 0) {
          setError(tUi('ACCOUNT_LOCKED_CONTACT'));
        } else {
          setError(tUi('ATTEMPTS_REMAINING').replace('{remaining}', String(remaining)));
        }
      } else if (errCode === 'LOCKED' || errCode === 'ACCOUNT_LOCKED') {
        setError(tUi('ACCOUNT_LOCKED_CONTACT'));
      } else if (errCode === 'EXPIRED') {
        setError(tUi('SESSION_EXPIRED'));
        setTimeout(() => router.replace('/(auth)/sign-in'), 2000);
      } else {
        setError(tUi('SOMETHING_WENT_WRONG'));
      }
      setCode('');
      shake();
      inputRef.current?.focus();
    } finally {
      setLoading(false);
    }
  }

  const digits = code.padEnd(CODE_LEN, '').split('');
  const warnLevel = attempts >= 3 ? 'high' : attempts >= 1 ? 'medium' : 'none';

  return (
    <LinearGradient colors={['#0F172A', colors.space2, colors.space]} locations={[0, 0.45, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={s.screen}>
      <View style={s.orb1} pointerEvents="none" />
      <View style={s.orb2} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        <Pressable onPress={() => router.back()} style={s.back}>
          <Text style={s.backText}>← Back</Text>
        </Pressable>

        <Animated.View style={[s.content, { opacity: fadeIn }]}>
          {/* Shield icon */}
          <View style={s.iconWrap}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.iconGrad}>
              <Text style={s.iconEmoji}>🛡️</Text>
            </LinearGradient>
          </View>

          <Text style={s.stepTag}>STEP 3 OF 3 — 2-FACTOR AUTH</Text>
          <Text style={s.title}>One more check</Text>
          <Text style={s.sub}>
            Open your authenticator app and enter the current 6-digit code for PRANA.
          </Text>

          {/* Countdown bar — 30-second TOTP window visual */}
          <TotpTimer />

          {/* Hidden input */}
          <TextInput
            ref={inputRef}
            value={code}
            onChangeText={v => { setCode(v.replace(/\D/g, '').slice(0, CODE_LEN)); setError(''); }}
            keyboardType="number-pad"
            maxLength={CODE_LEN}
            style={s.hiddenInput}
            editable={!loading}
          />

          {/* OTP boxes */}
          <Pressable onPress={() => inputRef.current?.focus()}>
            <Animated.View style={[s.otpRow, { transform: [{ translateX: shakeAnim }] }]}>
              {digits.map((d, i) => (
                <View key={i} style={[
                  s.otpBox,
                  i < code.length && s.otpBoxFilled,
                  i === code.length && s.otpBoxActive,
                  warnLevel === 'high' && s.otpBoxWarn,
                ]}>
                  {i < code.length
                    ? <Text style={s.otpDigit}>{d}</Text>
                    : <View style={[s.cursor, i === code.length && s.cursorActive]} />}
                </View>
              ))}
            </Animated.View>
          </Pressable>

          {/* Success overlay */}
          <Animated.View style={[s.successOverlay, { transform: [{ scale: successScale }], opacity: successScale }]}>
            <LinearGradient colors={['#34D399', '#22D3EE']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.successCircle}>
              <Text style={s.successTick}>✓</Text>
            </LinearGradient>
          </Animated.View>

          {/* Error / warning */}
          {error ? (
            <View style={[s.errorBox, warnLevel === 'high' && s.errorBoxHigh]}>
              <Text style={s.errorIcon}>{warnLevel === 'high' ? '🔒' : '⚠'}</Text>
              <Text style={s.errorText}>{error}</Text>
            </View>
          ) : null}

          {/* Attempt warning bar */}
          {warnLevel !== 'none' && !error && (
            <View style={[s.warnBar, warnLevel === 'high' && s.warnBarHigh]}>
              <Text style={s.warnText}>
                {tUi('ATTEMPTS_REMAINING').replace('{remaining}', String(5 - attempts))}
              </Text>
            </View>
          )}

          {loading && (
            <View style={s.loadingRow}>
              <ActivityIndicator size="small" color={colors.emerald} />
              <Text style={s.loadingText}>Verifying…</Text>
            </View>
          )}

          {/* Can't find code */}
          <Pressable onPress={() => router.replace('/(auth)/totp-setup')} style={s.helpBtn}>
            <Text style={s.helpText}>Can't find your code? Set up a new authenticator →</Text>
          </Pressable>
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

// 30-second TOTP countdown bar
function TotpTimer() {
  const progress = useRef(new Animated.Value(0)).current;
  const [secsLeft, setSecsLeft] = useState(0);

  useEffect(() => {
    function tick() {
      const now = Math.floor(Date.now() / 1000);
      const secs = 30 - (now % 30);
      setSecsLeft(secs);
      const frac = secs / 30;
      progress.setValue(frac);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const barColor = secsLeft <= 7 ? colors.rose : secsLeft <= 15 ? colors.amber : colors.emerald;

  return (
    <View style={timer.wrap}>
      <View style={timer.track}>
        <Animated.View style={[timer.fill, { flex: progress as unknown as number, backgroundColor: barColor }]} />
        <Animated.View style={[timer.gap, { flex: Animated.subtract(1, progress) as unknown as number }]} />
      </View>
      <Text style={[timer.label, { color: barColor }]}>Code refreshes in {secsLeft}s</Text>
    </View>
  );
}

const timer = StyleSheet.create({
  wrap: { marginBottom: 24 },
  track: { flexDirection: 'row', height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.08)', marginBottom: 6, overflow: 'hidden' },
  fill: { height: 3, borderRadius: 2 },
  gap: { height: 3 },
  label: { fontFamily: fonts.mono, fontSize: 10, textAlign: 'center' },
});

const s = StyleSheet.create({
  screen: { flex: 1 },
  orb1: { position: 'absolute', width: 200, height: 200, borderRadius: 100, backgroundColor: colors.indigo, opacity: 0.10, top: -50, right: -70 },
  orb2: { position: 'absolute', width: 160, height: 160, borderRadius: 80, backgroundColor: colors.emerald, opacity: 0.07, bottom: 100, left: -60 },
  safe: { flex: 1 },
  back: { paddingHorizontal: 24, paddingTop: 12, paddingBottom: 4 },
  backText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#6B7394' },
  content: { flex: 1, paddingHorizontal: 24, paddingTop: 12, alignItems: 'center' },

  iconWrap: { marginBottom: 16 },
  iconGrad: { width: 68, height: 68, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  iconEmoji: { fontSize: 30 },

  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.emerald, letterSpacing: 1.2, marginBottom: 8 },
  title: { fontFamily: fonts.displayBold, fontSize: 24, color: '#FFFFFF', letterSpacing: -0.3, marginBottom: 8, textAlign: 'center' },
  sub: { fontSize: 13, color: '#8B97B8', textAlign: 'center', lineHeight: 20, marginBottom: 20, paddingHorizontal: 16 },

  hiddenInput: { position: 'absolute', opacity: 0, height: 0, width: 0 },

  otpRow: { flexDirection: 'row', gap: 10, justifyContent: 'center', marginBottom: 20 },
  otpBox: {
    width: 46, height: 58, borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.10)',
    alignItems: 'center', justifyContent: 'center',
  },
  otpBoxFilled: { backgroundColor: 'rgba(99,102,241,0.12)', borderColor: colors.indigo },
  otpBoxActive: { borderColor: colors.cyan, shadowColor: colors.cyan, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.4, shadowRadius: 8 },
  otpBoxWarn: { borderColor: colors.rose },
  otpDigit: { fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF' },
  cursor: { width: 2, height: 22, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 1 },
  cursorActive: { backgroundColor: colors.cyan },

  successOverlay: { position: 'absolute', top: '35%' },
  successCircle: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center' },
  successTick: { fontSize: 32, color: '#04261C', fontWeight: '700' },

  errorBox: {
    flexDirection: 'row', gap: 8, alignItems: 'flex-start',
    backgroundColor: 'rgba(251,113,133,0.10)',
    borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 12, alignSelf: 'stretch',
  },
  errorBoxHigh: { backgroundColor: 'rgba(251,113,133,0.18)', borderColor: colors.rose },
  errorIcon: { fontSize: 14 },
  errorText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5' },

  warnBar: {
    backgroundColor: 'rgba(251,191,36,0.10)', borderWidth: 1, borderColor: 'rgba(251,191,36,0.20)',
    borderRadius: 10, padding: 10, alignSelf: 'stretch', marginBottom: 10,
  },
  warnBarHigh: { backgroundColor: 'rgba(251,113,133,0.10)', borderColor: 'rgba(251,113,133,0.25)' },
  warnText: { fontFamily: fonts.mono, fontSize: 11, color: colors.amber, textAlign: 'center' },

  loadingRow: { flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 12 },
  loadingText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.emerald },

  helpBtn: { marginTop: 'auto', paddingBottom: 32, paddingTop: 16 },
  helpText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#4B5268', textAlign: 'center', textDecorationLine: 'underline' },
});
