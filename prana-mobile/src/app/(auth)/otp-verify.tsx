import React, { useRef, useState, useEffect } from 'react';
import {
  View, Text, TextInput, StyleSheet, Pressable,
  ActivityIndicator, Animated, Easing,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, radius } from '@/prana-theme/tokens';
import { tError, tUi } from '@/i18n';

const CODE_LEN = 6;
const RESEND_WAIT = 30;

export default function OtpVerifyScreen() {
  const [code,     setCode]     = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [resendIn, setResendIn] = useState(RESEND_WAIT);
  const [resending, setResending] = useState(false);
  const [sent,     setSent]     = useState(false); // flash feedback on resend
  const inputRef  = useRef<TextInput>(null);
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const fadeIn    = useRef(new Animated.Value(0)).current;
  const successScale = useRef(new Animated.Value(0)).current;

  const mobile = authStore.getPendingMobile() ?? '';
  const maskedMobile = mobile ? `+91 ${mobile.slice(0, 2)}••••${mobile.slice(-4)}` : '';

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }).start();
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (resendIn <= 0) return;
    const t = setInterval(() => setResendIn(v => v <= 1 ? 0 : v - 1), 1000);
    return () => clearInterval(t);
  }, [resendIn]);

  // Auto-submit when all 6 digits are entered
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
      const res = await api.post<{
        step_token: string;
        has_totp: boolean;
        is_new_device: boolean;
        requires_consent: boolean;
      }>('/auth/employee/verify-otp', { mobile, code });

      authStore.setStepToken(res.step_token);

      // Animate success tick before navigating
      Animated.spring(successScale, { toValue: 1, friction: 4, tension: 200, useNativeDriver: true }).start();
      await new Promise(r => setTimeout(r, 500));

      if (res.requires_consent) {
        router.replace('/(auth)/consent');
      } else if (res.is_new_device) {
        router.replace('/(auth)/register-device');
      } else if (res.has_totp) {
        router.replace('/(auth)/totp-verify');
      } else {
        router.replace('/(auth)/totp-setup');
      }
    } catch (e: any) {
      const errCode = e?.body?.error ?? e?.response?.data?.error;
      if (errCode === 'INVALID_OTP')   setError(tError('INVALID_OTP'));
      else if (errCode === 'EXPIRED' || errCode === 'OTP_EXPIRED')  setError(tError('OTP_ALREADY_USED'));
      else if (errCode === 'LOCKED' || errCode === 'OTP_RATE_LIMITED') setError(tError('OTP_RATE_LIMITED'));
      else setError(tUi('SOMETHING_WENT_WRONG'));
      setCode('');
      shake();
      inputRef.current?.focus();
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (resendIn > 0 || resending) return;
    setResending(true);
    setError('');
    try {
      await api.post('/auth/employee/request-otp', { mobile });
      setResendIn(RESEND_WAIT);
      setSent(true);
      setTimeout(() => setSent(false), 3000);
      setCode('');
      inputRef.current?.focus();
    } catch {
      setError(tUi('OTP_RESEND_FAILED'));
    } finally {
      setResending(false);
    }
  }

  const digits = code.padEnd(CODE_LEN, '').split('');

  return (
    <LinearGradient colors={['#0F172A', colors.space2, colors.space]} locations={[0, 0.45, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={s.screen}>
      <View style={s.orb1} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        {/* Back */}
        <Pressable onPress={() => router.back()} style={s.back}>
          <Text style={s.backText}>← Back</Text>
        </Pressable>

        <Animated.View style={[s.content, { opacity: fadeIn }]}>
          {/* Header */}
          <View style={s.header}>
            <View style={s.iconWrap}>
              <Text style={s.iconEmoji}>💬</Text>
            </View>
            <Text style={s.stepTag}>STEP 2 OF 3 — VERIFY</Text>
            <Text style={s.title}>Check your messages</Text>
            <Text style={s.sub}>We sent a 6-digit code to{'\n'}<Text style={s.mobile}>{maskedMobile}</Text></Text>
          </View>

          {/* OTP boxes */}
          <TextInput
            ref={inputRef}
            value={code}
            onChangeText={v => { setCode(v.replace(/\D/g, '').slice(0, CODE_LEN)); setError(''); }}
            keyboardType="number-pad"
            maxLength={CODE_LEN}
            style={s.hiddenInput}
            autoFocus
            editable={!loading}
          />

          <Pressable onPress={() => inputRef.current?.focus()}>
            <Animated.View style={[s.otpRow, { transform: [{ translateX: shakeAnim }] }]}>
              {digits.map((d, i) => {
                const isFilled = i < code.length;
                const isActive = i === code.length;
                return (
                  <View key={i} style={[
                    s.otpBox,
                    isFilled && s.otpBoxFilled,
                    isActive && s.otpBoxActive,
                  ]}>
                    {isFilled ? (
                      <Text style={s.otpDigit}>{d}</Text>
                    ) : (
                      <View style={[s.otpCursor, isActive && s.otpCursorActive]} />
                    )}
                  </View>
                );
              })}
            </Animated.View>
          </Pressable>

          {/* Success tick overlay */}
          <Animated.View style={[s.successTick, { transform: [{ scale: successScale }], opacity: successScale }]}>
            <LinearGradient colors={['#34D399', '#22D3EE']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.tickCircle}>
              <Text style={s.tickText}>✓</Text>
            </LinearGradient>
          </Animated.View>

          {/* Error */}
          {error ? (
            <View style={s.errorBox}>
              <Text style={s.errorIcon}>⚠</Text>
              <Text style={s.errorText}>{error}</Text>
            </View>
          ) : sent ? (
            <View style={s.sentBox}>
              <Text style={s.sentText}>✓ New code sent</Text>
            </View>
          ) : null}

          {/* Loading */}
          {loading && (
            <View style={s.loadingRow}>
              <ActivityIndicator size="small" color={colors.emerald} />
              <Text style={s.loadingText}>Verifying…</Text>
            </View>
          )}

          {/* Resend */}
          <View style={s.resendRow}>
            <Text style={s.resendLabel}>Didn't receive it? </Text>
            {resendIn > 0 ? (
              <Text style={s.resendTimer}>Resend in {resendIn}s</Text>
            ) : resending ? (
              <ActivityIndicator size="small" color={colors.indigo} />
            ) : (
              <Pressable onPress={handleResend}>
                <Text style={s.resendLink}>Resend code</Text>
              </Pressable>
            )}
          </View>

          {/* Security note */}
          <View style={s.secNote}>
            <Text style={s.secNoteText}>🔒  This code expires in 10 minutes · Never share it with anyone</Text>
          </View>
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1 },
  orb1: { position: 'absolute', width: 240, height: 240, borderRadius: 120, backgroundColor: colors.indigo, opacity: 0.10, top: -60, right: -80 },
  safe: { flex: 1 },
  back: { paddingHorizontal: 24, paddingTop: 12, paddingBottom: 4 },
  backText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#6B7394' },
  content: { flex: 1, paddingHorizontal: 24, paddingTop: 8 },

  header: { alignItems: 'center', marginBottom: 36 },
  iconWrap: {
    width: 64, height: 64, borderRadius: 20,
    backgroundColor: 'rgba(99,102,241,0.12)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.2)',
    alignItems: 'center', justifyContent: 'center', marginBottom: 16,
  },
  iconEmoji: { fontSize: 28 },
  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.emerald, letterSpacing: 1.2, marginBottom: 8 },
  title: { fontFamily: fonts.displayBold, fontSize: 24, color: '#FFFFFF', letterSpacing: -0.3, marginBottom: 8, textAlign: 'center' },
  sub: { fontSize: 13, color: '#8B97B8', textAlign: 'center', lineHeight: 20 },
  mobile: { fontFamily: fonts.mono, color: '#FFFFFF' },

  hiddenInput: { position: 'absolute', opacity: 0, height: 0, width: 0 },

  otpRow: { flexDirection: 'row', gap: 10, justifyContent: 'center', marginBottom: 24 },
  otpBox: {
    width: 46, height: 58, borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.10)',
    alignItems: 'center', justifyContent: 'center',
  },
  otpBoxFilled: { backgroundColor: 'rgba(99,102,241,0.12)', borderColor: colors.indigo },
  otpBoxActive: {
    borderColor: colors.cyan,
    shadowColor: colors.cyan, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.4, shadowRadius: 8,
  },
  otpDigit: { fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF' },
  otpCursor: { width: 2, height: 22, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 1 },
  otpCursorActive: { backgroundColor: colors.cyan },

  successTick: { position: 'absolute', alignSelf: 'center', top: '38%' },
  tickCircle: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center' },
  tickText: { fontSize: 32, color: '#04261C', fontWeight: '700' },

  errorBox: {
    flexDirection: 'row', gap: 8, alignItems: 'flex-start',
    backgroundColor: 'rgba(251,113,133,0.10)',
    borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 16,
  },
  errorIcon: { fontSize: 14, color: colors.rose },
  errorText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5' },

  sentBox: {
    backgroundColor: 'rgba(52,211,153,0.10)', borderRadius: 12, padding: 12,
    alignItems: 'center', marginBottom: 16,
  },
  sentText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.emerald },

  loadingRow: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  loadingText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.emerald },

  resendRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 24 },
  resendLabel: { fontSize: 13, color: '#6B7394' },
  resendTimer: { fontFamily: fonts.mono, fontSize: 13, color: '#6B7394' },
  resendLink: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo, textDecorationLine: 'underline' },

  secNote: {
    backgroundColor: 'rgba(52,211,153,0.06)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.12)',
    borderRadius: 12, padding: 12,
  },
  secNoteText: { fontFamily: fonts.mono, fontSize: 10, color: '#4B8B6B', textAlign: 'center', lineHeight: 16 },
});
