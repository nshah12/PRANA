import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, Pressable, ActivityIndicator,
  TextInput, Animated, ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, radius } from '@/prana-theme/tokens';

// QR code rendered as SVG-like grid using the returned svg string in a WebView,
// or via a native QR library. Here we use a real API response that includes
// the otpauth:// URI and display the manual key as a copy-fallback.
// In production: swap the <QrPlaceholder> with react-native-qrcode-svg.

const CODE_LEN = 6;

function QrDisplay({ uri, secretKey }: { uri: string; secretKey: string }) {
  const [copied, setCopied] = useState(false);

  // Dynamically import QR — safe fallback if library absent
  let QRCode: React.ComponentType<{ value: string; size: number; color: string; backgroundColor: string }> | null = null;
  try {
    QRCode = require('react-native-qrcode-svg').default;
  } catch {}

  async function copyKey() {
    const Clipboard = (await import('@react-native-clipboard/clipboard')).default;
    Clipboard.setString(secretKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <View style={qr.wrap}>
      <View style={qr.qrFrame}>
        {QRCode ? (
          <QRCode value={uri} size={160} color="#0B0F1E" backgroundColor="#FFFFFF" />
        ) : (
          <View style={qr.qrFallback}>
            <Text style={qr.qrFallbackText}>QR not available{'\n'}Use the key below</Text>
          </View>
        )}
      </View>

      <Text style={qr.scanHint}>Open Google Authenticator, Authy, or any TOTP app and scan this code</Text>

      <View style={qr.keyRow}>
        <View style={{ flex: 1 }}>
          <Text style={qr.keyLabel}>MANUAL ENTRY KEY</Text>
          <Text style={qr.keyValue} selectable>{secretKey.match(/.{1,4}/g)?.join(' ') ?? secretKey}</Text>
        </View>
        <Pressable onPress={copyKey} style={qr.copyBtn}>
          <Text style={qr.copyText}>{copied ? '✓ Copied' : 'Copy'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const qr = StyleSheet.create({
  wrap: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    borderRadius: 22, padding: 20, marginBottom: 16, alignItems: 'center',
  },
  qrFrame: {
    width: 180, height: 180, borderRadius: 16,
    backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center',
    padding: 10, marginBottom: 14,
  },
  qrFallback: { alignItems: 'center', justifyContent: 'center', flex: 1 },
  qrFallbackText: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink2, textAlign: 'center' },
  scanHint: { fontFamily: fonts.bodyRegular, fontSize: 12, color: '#8B97B8', textAlign: 'center', lineHeight: 18, marginBottom: 14 },
  keyRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)',
    borderRadius: 14, padding: 12, gap: 10, alignSelf: 'stretch',
  },
  keyLabel: { fontFamily: fonts.mono, fontSize: 9, color: '#6B7394', letterSpacing: 1, marginBottom: 4 },
  keyValue: { fontFamily: fonts.mono, fontSize: 13, color: '#FFFFFF', letterSpacing: 2 },
  copyBtn: {
    backgroundColor: 'rgba(99,102,241,0.15)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.25)',
    borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6,
  },
  copyText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.indigo },
});

// ── Screen ────────────────────────────────────────────────────────────────────
export default function TotpSetupScreen() {
  const [phase, setPhase] = useState<'loading' | 'scan' | 'verify' | 'error'>('loading');
  const [totpUri, setTotpUri] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState('');
  const inputRef = useRef<TextInput>(null);
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const fadeIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }).start();
    loadTotpSetup();
  }, []);

  useEffect(() => {
    if (code.length === CODE_LEN && phase === 'verify') handleVerify();
  }, [code]);

  async function loadTotpSetup() {
    try {
      const stepToken = authStore.getStepToken();
      const res = await api.post<{ totp_uri: string; secret_key: string }>(
        '/auth/employee/totp-setup/init',
        { step_token: stepToken },
      );
      setTotpUri(res.totp_uri);
      setSecretKey(res.secret_key);
      setPhase('scan');
    } catch {
      setPhase('error');
    }
  }

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
    if (code.length !== CODE_LEN || verifying) return;
    setVerifyError('');
    setVerifying(true);
    try {
      const stepToken = authStore.getStepToken();
      const res = await api.post<{ access_token: string }>(
        '/auth/employee/totp-setup/confirm',
        { step_token: stepToken, code },
      );
      authStore.setToken(res.access_token);
      authStore.clearStepToken();
      router.replace('/(auth)/register-device');
    } catch (e: any) {
      const errCode = e?.body?.error ?? e?.response?.data?.error;
      if (errCode === 'INVALID_TOTP') setVerifyError('Wrong code. Double-check the time on your phone and try again.');
      else setVerifyError('Verification failed. Try again.');
      setCode('');
      shake();
      inputRef.current?.focus();
    } finally {
      setVerifying(false);
    }
  }

  const digits = code.padEnd(CODE_LEN, '').split('');

  return (
    <LinearGradient colors={['#0F172A', colors.space2, colors.space]} locations={[0, 0.45, 1]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={s.screen}>
      <View style={s.orb1} pointerEvents="none" />
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
          <Animated.View style={{ opacity: fadeIn }}>
            {/* Brand + step */}
            <View style={s.topRow}>
              <LinearGradient colors={['#6366F1', '#22D3EE', '#34D399']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.brandMark}>
                <Text style={s.brandIcon}>P</Text>
              </LinearGradient>
              <Text style={s.stepTag}>STEP 3 OF 3 — SECURE YOUR VAULT</Text>
            </View>

            <Text style={s.title}>Set up authenticator</Text>
            <Text style={s.sub}>
              2-factor authentication adds a second lock to your vault.{'\n'}
              Even if someone knows your mobile number, they can't get in.
            </Text>

            {/* Why it matters strip */}
            <View style={s.whyStrip}>
              <View style={s.whyItem}>
                <Text style={s.whyIcon}>🛡️</Text>
                <Text style={s.whyText}>Blocks SIM-swap attacks</Text>
              </View>
              <View style={s.whyDivider} />
              <View style={s.whyItem}>
                <Text style={s.whyIcon}>⚡</Text>
                <Text style={s.whyText}>30-second rotating codes</Text>
              </View>
              <View style={s.whyDivider} />
              <View style={s.whyItem}>
                <Text style={s.whyIcon}>📴</Text>
                <Text style={s.whyText}>Works offline</Text>
              </View>
            </View>

            {/* Main content by phase */}
            {phase === 'loading' && (
              <View style={s.loadingWrap}>
                <ActivityIndicator color={colors.emerald} size="large" />
                <Text style={s.loadingText}>Generating your secure key…</Text>
              </View>
            )}

            {phase === 'error' && (
              <View style={s.errorWrap}>
                <Text style={s.errorWrapText}>Could not generate TOTP setup. Check your connection.</Text>
                <Pressable onPress={loadTotpSetup} style={s.retryBtn}>
                  <Text style={s.retryText}>Try again</Text>
                </Pressable>
              </View>
            )}

            {(phase === 'scan' || phase === 'verify') && (
              <>
                <QrDisplay uri={totpUri} secretKey={secretKey} />

                {/* Phase toggle */}
                <View style={s.phaseToggle}>
                  <Pressable
                    onPress={() => setPhase('scan')}
                    style={[s.phaseTab, phase === 'scan' && s.phaseTabActive]}
                  >
                    <Text style={[s.phaseTabText, phase === 'scan' && s.phaseTabTextActive]}>1. Scan QR</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => { setPhase('verify'); setTimeout(() => inputRef.current?.focus(), 100); }}
                    style={[s.phaseTab, phase === 'verify' && s.phaseTabActive]}
                  >
                    <Text style={[s.phaseTabText, phase === 'verify' && s.phaseTabTextActive]}>2. Enter code</Text>
                  </Pressable>
                </View>

                {phase === 'verify' && (
                  <View style={s.verifySection}>
                    <Text style={s.verifyLabel}>Enter the 6-digit code from your authenticator app</Text>

                    <TextInput
                      ref={inputRef}
                      value={code}
                      onChangeText={v => { setCode(v.replace(/\D/g, '').slice(0, CODE_LEN)); setVerifyError(''); }}
                      keyboardType="number-pad"
                      maxLength={CODE_LEN}
                      style={s.hiddenInput}
                      autoFocus
                      editable={!verifying}
                    />

                    <Pressable onPress={() => inputRef.current?.focus()}>
                      <Animated.View style={[s.otpRow, { transform: [{ translateX: shakeAnim }] }]}>
                        {digits.map((d, i) => (
                          <View key={i} style={[
                            s.otpBox,
                            i < code.length && s.otpBoxFilled,
                            i === code.length && s.otpBoxActive,
                          ]}>
                            <Text style={s.otpDigit}>{d}</Text>
                          </View>
                        ))}
                      </Animated.View>
                    </Pressable>

                    {verifyError ? (
                      <View style={s.errorBox}>
                        <Text style={s.errorText}>{verifyError}</Text>
                      </View>
                    ) : null}

                    {verifying && (
                      <View style={s.verifyingRow}>
                        <ActivityIndicator size="small" color={colors.emerald} />
                        <Text style={s.verifyingText}>Confirming…</Text>
                      </View>
                    )}

                    {!verifying && code.length === CODE_LEN && (
                      <Pressable onPress={handleVerify} style={s.confirmBtn}>
                        <LinearGradient colors={['#6366F1', '#22D3EE', '#34D399']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.confirmGrad}>
                          <Text style={s.confirmText}>Confirm & activate 2FA →</Text>
                        </LinearGradient>
                      </Pressable>
                    )}
                  </View>
                )}
              </>
            )}

            {/* Recommended apps */}
            <View style={s.appsNote}>
              <Text style={s.appsLabel}>RECOMMENDED APPS</Text>
              <Text style={s.appsText}>Google Authenticator · Authy · Microsoft Authenticator · 1Password</Text>
            </View>
          </Animated.View>
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1 },
  orb1: { position: 'absolute', width: 220, height: 220, borderRadius: 110, backgroundColor: colors.indigo, opacity: 0.09, top: -60, right: -70 },
  safe: { flex: 1 },
  scroll: { paddingHorizontal: 24, paddingTop: 16, paddingBottom: 48 },

  topRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 20 },
  brandMark: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },
  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.emerald, letterSpacing: 1.2 },

  title: { fontFamily: fonts.displayBold, fontSize: 24, color: '#FFFFFF', letterSpacing: -0.3, marginBottom: 8 },
  sub: { fontSize: 13, color: '#8B97B8', lineHeight: 20, marginBottom: 18 },

  whyStrip: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(99,102,241,0.08)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.15)',
    borderRadius: 16, padding: 14, marginBottom: 20,
  },
  whyItem: { flex: 1, alignItems: 'center', gap: 4 },
  whyIcon: { fontSize: 18 },
  whyText: { fontFamily: fonts.mono, fontSize: 9, color: '#8B97B8', textAlign: 'center', lineHeight: 13 },
  whyDivider: { width: 1, height: 32, backgroundColor: 'rgba(255,255,255,0.08)' },

  loadingWrap: { alignItems: 'center', paddingVertical: 48, gap: 16 },
  loadingText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: '#8B97B8' },

  errorWrap: { alignItems: 'center', paddingVertical: 32, gap: 14 },
  errorWrapText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: '#FCA5A5', textAlign: 'center' },
  retryBtn: {
    backgroundColor: 'rgba(99,102,241,0.15)', borderWidth: 1, borderColor: 'rgba(99,102,241,0.25)',
    borderRadius: 14, paddingHorizontal: 20, paddingVertical: 10,
  },
  retryText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo },

  phaseToggle: {
    flexDirection: 'row', backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)',
    borderRadius: 14, padding: 4, marginBottom: 16,
  },
  phaseTab: { flex: 1, borderRadius: 10, paddingVertical: 10, alignItems: 'center' },
  phaseTabActive: { backgroundColor: 'rgba(99,102,241,0.18)' },
  phaseTabText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#6B7394' },
  phaseTabTextActive: { color: '#FFFFFF' },

  verifySection: { marginBottom: 16 },
  verifyLabel: { fontSize: 13, color: '#8B97B8', textAlign: 'center', marginBottom: 18 },

  hiddenInput: { position: 'absolute', opacity: 0, height: 0, width: 0 },

  otpRow: { flexDirection: 'row', gap: 10, justifyContent: 'center', marginBottom: 16 },
  otpBox: {
    width: 46, height: 56, borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.10)',
    alignItems: 'center', justifyContent: 'center',
  },
  otpBoxFilled: { backgroundColor: 'rgba(99,102,241,0.12)', borderColor: colors.indigo },
  otpBoxActive: { borderColor: colors.cyan, shadowColor: colors.cyan, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.35, shadowRadius: 6 },
  otpDigit: { fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF' },

  errorBox: {
    backgroundColor: 'rgba(251,113,133,0.10)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 12,
  },
  errorText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5', textAlign: 'center' },

  verifyingRow: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  verifyingText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.emerald },

  confirmBtn: { marginTop: 4 },
  confirmGrad: { borderRadius: 16, height: 54, alignItems: 'center', justifyContent: 'center' },
  confirmText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },

  appsNote: {
    marginTop: 20, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)',
    paddingTop: 16, alignItems: 'center', gap: 6,
  },
  appsLabel: { fontFamily: fonts.mono, fontSize: 9, color: '#4B5268', letterSpacing: 1.2 },
  appsText: { fontFamily: fonts.bodyRegular, fontSize: 11, color: '#6B7394', textAlign: 'center' },
});
