/**
 * Enable Face ID screen.
 *
 * Emotional job: "Your face IS the key. No password. No code. Just you."
 *
 * This is an offer, not a requirement. The user has already verified
 * their identity. We're offering them a better door to their vault.
 *
 * API: POST /auth/employee/device/enroll-biometric
 *   body: { step_token, device_id }
 *   → { enrolled: true }
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, Animated, Easing,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as LocalAuthentication from 'expo-local-authentication';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

// ── Biometric scanner visual ──────────────────────────────────────────────────
function ScannerOrb({ scanning }: { scanning: boolean }) {
  const ring1 = useRef(new Animated.Value(1)).current;
  const ring2 = useRef(new Animated.Value(1)).current;
  const glow  = useRef(new Animated.Value(0.3)).current;
  const appear = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(appear, { toValue: 1, friction: 4, tension: 140, useNativeDriver: true }).start();
  }, []);

  useEffect(() => {
    if (!scanning) return;
    // Ripple rings out
    const r1 = Animated.loop(
      Animated.sequence([
        Animated.timing(ring1, { toValue: 1.35, duration: 1000, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(ring1, { toValue: 1.00, duration: 0,   useNativeDriver: true }),
      ])
    );
    const r2 = Animated.loop(
      Animated.sequence([
        Animated.delay(400),
        Animated.timing(ring2, { toValue: 1.35, duration: 1000, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(ring2, { toValue: 1.00, duration: 0,   useNativeDriver: true }),
      ])
    );
    const gl = Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(glow, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    r1.start(); r2.start(); gl.start();
    return () => { r1.stop(); r2.stop(); gl.stop(); };
  }, [scanning]);

  return (
    <Animated.View style={[orb.wrap, { transform: [{ scale: appear }] }]}>
      {/* Ripple rings */}
      <Animated.View style={[orb.ring, { transform: [{ scale: ring1 }], opacity: ring1.interpolate({ inputRange: [1, 1.35], outputRange: [0.3, 0] }) }]} />
      <Animated.View style={[orb.ring, { transform: [{ scale: ring2 }], opacity: ring2.interpolate({ inputRange: [1, 1.35], outputRange: [0.25, 0] }) }]} />

      {/* Center glow */}
      <Animated.View style={[orb.glow, { opacity: glow }]} />

      {/* Face outline */}
      <LinearGradient
        colors={gradJourney.colors}
        locations={gradJourney.locations}
        start={gradJourney.start}
        end={gradJourney.end}
        style={orb.grad}
      >
        <Text style={orb.faceEmoji}>🫥</Text>
        {scanning && (
          <View style={orb.scanLine} />
        )}
      </LinearGradient>
    </Animated.View>
  );
}

const orb = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center', width: 140, height: 140 },
  ring: {
    position: 'absolute',
    width: 140, height: 140, borderRadius: 70,
    borderWidth: 2, borderColor: colors.cyan,
  },
  glow: {
    position: 'absolute',
    width: 110, height: 110, borderRadius: 55,
    backgroundColor: colors.indigo,
  },
  grad: {
    width: 96, height: 96, borderRadius: 30,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  faceEmoji: { fontSize: 44 },
  scanLine: {
    position: 'absolute', left: 0, right: 0,
    height: 2, backgroundColor: 'rgba(52,211,153,0.7)',
    top: '50%',
  },
});

// ── Screen ────────────────────────────────────────────────────────────────────
export default function EnableFaceIdScreen() {
  const [scanning,  setScanning]  = useState(false);
  const [status,    setStatus]    = useState<'idle' | 'enrolling' | 'done' | 'error'>('idle');
  const [errorMsg,  setErrorMsg]  = useState('');
  const [biometricType, setBiometricType] = useState<'face' | 'fingerprint' | 'none'>('face');
  const fadeIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 600, useNativeDriver: true }).start();
    detectBiometricType();
  }, []);

  async function detectBiometricType() {
    try {
      const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
      if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
        setBiometricType('face');
      } else if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
        setBiometricType('fingerprint');
      } else {
        setBiometricType('none');
      }
    } catch {
      setBiometricType('face'); // safe default
    }
  }

  async function handleEnable() {
    setScanning(true);
    setStatus('enrolling');
    setErrorMsg('');
    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Authenticate to enable biometric unlock for your PRANA vault',
        fallbackLabel: 'Use passcode',
        cancelLabel: 'Cancel',
        disableDeviceFallback: false,
      });

      if (!result.success) {
        setScanning(false);
        setStatus('idle');
        if (result.error !== 'user_cancel') {
          setErrorMsg('Biometric authentication failed. Try again or skip for now.');
        }
        return;
      }

      // Enroll with backend — server stores a flag that this device uses biometrics
      const stepToken = authStore.getStepToken();
      const deviceId  = authStore.getDeviceId?.() ?? 'unknown';
      await api.post('/auth/employee/device/enroll-biometric', {
        step_token: stepToken,
        device_id:  deviceId,
      });

      setScanning(false);
      setStatus('done');

      // Navigate after brief success moment
      setTimeout(() => router.replace('/(auth)/consent'), 900);
    } catch {
      setScanning(false);
      setStatus('error');
      setErrorMsg('Could not complete enrollment. You can enable this later in Settings.');
    }
  }

  function handleSkip() {
    router.replace('/(auth)/consent');
  }

  const label = biometricType === 'fingerprint' ? 'fingerprint' : 'Face ID';
  const labelCap = biometricType === 'fingerprint' ? 'Fingerprint' : 'Face ID';
  const emoji = biometricType === 'fingerprint' ? '👆' : '🫥';

  return (
    <LinearGradient
      colors={['#080D1A', '#0F172A', '#131B33']}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={s.screen}
    >
      <View style={s.orbTL} pointerEvents="none" />
      <View style={s.orbBR} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        <Animated.View style={[s.content, { opacity: fadeIn }]}>

          {/* Orb */}
          <View style={s.orbWrap}>
            <ScannerOrb scanning={scanning} />
          </View>

          {/* Copy */}
          <Text style={s.stepTag}>YOUR KEY, YOUR VAULT</Text>
          <Text style={s.title}>
            {status === 'done'
              ? `${labelCap} enrolled.`
              : `Make your ${label}\nthe key to your vault.`}
          </Text>
          <Text style={s.sub}>
            {status === 'done'
              ? 'Your vault will open the moment it recognises you. No code, no wait.'
              : `A single glance ${biometricType === 'fingerprint' ? 'or touch' : ''} opens your vault instantly. Your biometric data never leaves this device — we only store an encrypted unlock signal.`}
          </Text>

          {/* What this gives you */}
          {status === 'idle' && (
            <View style={s.benefitCard}>
              <BenefitRow icon="⚡" text={`Opens vault in under a second`} />
              <BenefitRow icon="📴" text={`Works offline — no internet needed`} />
              <BenefitRow icon="🔒" text={`Biometric data stays on-device always`} />
              <BenefitRow icon="🔑" text={`Revocable from Settings any time`} />
            </View>
          )}

          {errorMsg ? (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{errorMsg}</Text>
            </View>
          ) : null}

          {/* CTAs */}
          {status === 'idle' || status === 'error' ? (
            <>
              <Pressable
                onPress={handleEnable}
                style={({ pressed }) => [s.ctaWrap, pressed && { opacity: 0.85 }]}
              >
                <LinearGradient
                  colors={gradJourney.colors}
                  locations={gradJourney.locations}
                  start={gradJourney.start}
                  end={gradJourney.end}
                  style={s.cta}
                >
                  <Text style={s.ctaText}>Enable {labelCap}  {emoji}</Text>
                </LinearGradient>
              </Pressable>
              <Pressable onPress={handleSkip} style={s.skipBtn}>
                <Text style={s.skipText}>Skip for now — I'll enable it later</Text>
              </Pressable>
            </>
          ) : status === 'enrolling' ? (
            <View style={s.enrollingRow}>
              <Text style={s.enrollingText}>Hold still…</Text>
            </View>
          ) : (
            <View style={s.successRow}>
              <LinearGradient colors={['#34D399', '#22D3EE']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.successCircle}>
                <Text style={s.successTick}>✓</Text>
              </LinearGradient>
              <Text style={s.successText}>Opening your vault…</Text>
            </View>
          )}
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

function BenefitRow({ icon, text }: { icon: string; text: string }) {
  return (
    <View style={br.row}>
      <Text style={br.icon}>{icon}</Text>
      <Text style={br.text}>{text}</Text>
    </View>
  );
}
const br = StyleSheet.create({
  row:  { flexDirection: 'row', gap: 10, alignItems: 'center', paddingVertical: 7 },
  icon: { fontSize: 16, width: 24, textAlign: 'center' },
  text: { fontFamily: fonts.bodyMedium, fontSize: 13, color: '#8B97B8' },
});

const s = StyleSheet.create({
  screen: { flex: 1 },
  orbTL: { position: 'absolute', width: 220, height: 220, borderRadius: 110, backgroundColor: colors.indigo, opacity: 0.07, top: -60, left: -80 },
  orbBR: { position: 'absolute', width: 180, height: 180, borderRadius: 90, backgroundColor: colors.emerald, opacity: 0.05, bottom: 60, right: -70 },
  safe: { flex: 1 },
  content: { flex: 1, paddingHorizontal: 28, paddingTop: 24, paddingBottom: 40 },

  orbWrap: { alignItems: 'center', marginBottom: 32, marginTop: 12 },

  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.emerald, letterSpacing: 1.5, marginBottom: 10, textAlign: 'center' },
  title: {
    fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF',
    letterSpacing: -0.4, lineHeight: 33, marginBottom: 12, textAlign: 'center',
  },
  sub: { fontSize: 13, color: '#6B7A9A', lineHeight: 21, marginBottom: 24, textAlign: 'center' },

  benefitCard: {
    backgroundColor: 'rgba(255,255,255,0.035)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18, paddingHorizontal: 16, paddingVertical: 6, marginBottom: 24,
  },

  errorBox: {
    backgroundColor: 'rgba(251,113,133,0.10)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 16,
  },
  errorText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5', textAlign: 'center' },

  ctaWrap: { marginBottom: 10 },
  cta: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  ctaText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },

  skipBtn: { alignItems: 'center', paddingVertical: 14 },
  skipText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#3D4A6B', textDecorationLine: 'underline' },

  enrollingRow: { alignItems: 'center', paddingVertical: 20 },
  enrollingText: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.cyan },

  successRow: { alignItems: 'center', gap: 12, paddingVertical: 16 },
  successCircle: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center' },
  successTick: { fontSize: 26, color: '#04261C', fontWeight: '700' },
  successText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.emerald },
});
