/**
 * Biometric unlock screen — returning user, trusted device.
 *
 * Emotional job: "Your vault knows you. One look and you're in."
 *
 * This should feel like the vault OPENING for you — not a security
 * gate you pass through. The visual is the vault recognising the user,
 * not the user proving themselves to the vault.
 *
 * API: POST /auth/employee/biometric-verify
 *   body: { device_id, biometric_signature }
 *   → { access_token }
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
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

// ── Recognition orb ───────────────────────────────────────────────────────────
// States: waiting → scanning → success → fail
type OrbState = 'waiting' | 'scanning' | 'success' | 'fail';

function RecognitionOrb({ state }: { state: OrbState }) {
  const pulse = useRef(new Animated.Value(1)).current;
  const ringOpacity = useRef(new Animated.Value(0.4)).current;
  const checkScale = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (state === 'waiting') {
      // Gentle breathing — "I'm waiting for you"
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.05, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1.00, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        ])
      ).start();
      Animated.loop(
        Animated.sequence([
          Animated.timing(ringOpacity, { toValue: 0.6, duration: 1800, useNativeDriver: true }),
          Animated.timing(ringOpacity, { toValue: 0.2, duration: 1800, useNativeDriver: true }),
        ])
      ).start();
    }
    if (state === 'success') {
      Animated.spring(checkScale, { toValue: 1, friction: 4, tension: 200, useNativeDriver: true }).start();
    }
  }, [state]);

  const gradColors: [string, string, string] =
    state === 'success' ? ['#34D399', '#22D3EE', '#6366F1'] :
    state === 'fail'    ? ['#FB7185', '#F43F5E', '#E11D48'] :
    gradJourney.colors as unknown as [string, string, string];

  return (
    <View style={ro.wrap}>
      {/* Outer breathing ring */}
      <Animated.View style={[ro.outerRing, {
        opacity: ringOpacity,
        transform: [{ scale: pulse }],
        borderColor: state === 'fail' ? colors.rose : colors.indigo,
      }]} />

      {/* Mid ring */}
      <Animated.View style={[ro.midRing, {
        borderColor: state === 'fail' ? colors.rose : colors.cyan,
        opacity: state === 'scanning' ? 1 : 0.3,
      }]} />

      {/* Core */}
      <Animated.View style={{ transform: [{ scale: pulse }] }}>
        <LinearGradient
          colors={gradColors}
          locations={gradJourney.locations}
          start={gradJourney.start}
          end={gradJourney.end}
          style={ro.core}
        >
          {state === 'success' ? (
            <Animated.Text style={[ro.successTick, { transform: [{ scale: checkScale }] }]}>✓</Animated.Text>
          ) : state === 'fail' ? (
            <Text style={ro.failX}>✕</Text>
          ) : (
            <Text style={ro.faceEmoji}>🫥</Text>
          )}
        </LinearGradient>
      </Animated.View>
    </View>
  );
}

const ro = StyleSheet.create({
  wrap:      { width: 160, height: 160, alignItems: 'center', justifyContent: 'center' },
  outerRing: { position: 'absolute', width: 156, height: 156, borderRadius: 78, borderWidth: 1.5 },
  midRing:   { position: 'absolute', width: 128, height: 128, borderRadius: 64, borderWidth: 1 },
  core:      { width: 100, height: 100, borderRadius: 32, alignItems: 'center', justifyContent: 'center' },
  faceEmoji: { fontSize: 46 },
  successTick: { fontSize: 42, color: '#04261C', fontWeight: '700' },
  failX:     { fontSize: 38, color: '#FFFFFF', fontWeight: '700' },
});

// ── Screen ────────────────────────────────────────────────────────────────────
export default function BiometricUnlockScreen() {
  const { signIn, profile } = useAuth();
  const [orbState, setOrbState] = useState<OrbState>('waiting');
  const [error,    setError]    = useState('');
  const fadeIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 600, useNativeDriver: true }).start();
    // Auto-trigger on mount after brief moment for orientation
    const t = setTimeout(() => triggerBiometric(), 600);
    return () => clearTimeout(t);
  }, []);

  async function triggerBiometric() {
    setOrbState('scanning');
    setError('');
    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Unlock your PRANA vault',
        fallbackLabel: 'Enter passcode',
        cancelLabel: 'Sign in another way',
        disableDeviceFallback: false,
      });

      if (!result.success) {
        if (result.error === 'user_cancel') {
          setOrbState('waiting');
        } else {
          setOrbState('fail');
          setError('Biometric check failed. Try again or sign in another way.');
        }
        return;
      }

      // Exchange biometric success for an access token
      const deviceId = authStore.getDeviceId?.() ?? 'unknown';
      const res = await api.post<{ access_token: string }>(
        '/auth/employee/biometric-verify',
        { device_id: deviceId, verified: true },
      );

      setOrbState('success');
      signIn(res.access_token);
      setTimeout(() => router.replace('/(vault)/vault'), 700);
    } catch {
      setOrbState('fail');
      setError('Couldn\'t verify. Try again or sign in with OTP.');
    }
  }

  // Greeting — show name if available from SecureStore cache
  const name = profile?.name?.split(' ')[0] ?? '';

  return (
    <LinearGradient
      colors={['#080D1A', '#0F172A', '#131B33']}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={s.screen}
    >
      <View style={s.orbTL} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        <Animated.View style={[s.content, { opacity: fadeIn }]}>

          {/* Brand */}
          <View style={s.brandRow}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.brandMark}>
              <Text style={s.brandIcon}>P</Text>
            </LinearGradient>
            <Text style={s.brandName}>PRANA</Text>
          </View>

          {/* Main orb */}
          <View style={s.orbWrap}>
            <RecognitionOrb state={orbState} />
          </View>

          {/* Dynamic copy changes with state */}
          <Text style={s.greeting}>
            {orbState === 'waiting'  && (name ? `Welcome back, ${name}.` : 'Welcome back.')}
            {orbState === 'scanning' && 'Verifying…'}
            {orbState === 'success'  && 'Vault unlocked.'}
            {orbState === 'fail'     && 'Not recognised.'}
          </Text>
          <Text style={s.sub}>
            {orbState === 'waiting'  && 'Your vault is ready.\nJust look at your phone.'}
            {orbState === 'scanning' && 'Hold still for a moment…'}
            {orbState === 'success'  && 'Opening your vault now…'}
            {orbState === 'fail'     && (error || 'Biometric check failed.')}
          </Text>

          {/* Security assurance — always visible */}
          <View style={s.assurance}>
            <Text style={s.assuranceText}>🔒  Biometric data stays on-device · Never sent to PRANA servers</Text>
          </View>

          {/* CTAs based on state */}
          <View style={s.actions}>
            {(orbState === 'waiting' || orbState === 'fail') && (
              <Pressable
                onPress={triggerBiometric}
                style={({ pressed }) => [s.primaryBtn, pressed && { opacity: 0.85 }]}
              >
                <LinearGradient
                  colors={gradJourney.colors}
                  locations={gradJourney.locations}
                  start={gradJourney.start}
                  end={gradJourney.end}
                  style={s.primaryGrad}
                >
                  <Text style={s.primaryText}>
                    {orbState === 'fail' ? 'Try again' : 'Unlock vault'}
                  </Text>
                </LinearGradient>
              </Pressable>
            )}

            <Pressable onPress={() => router.replace('/(auth)/sign-in')} style={s.altBtn}>
              <Text style={s.altText}>Sign in another way</Text>
            </Pressable>
          </View>
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1 },
  orbTL:  { position: 'absolute', width: 240, height: 240, borderRadius: 120, backgroundColor: colors.indigo, opacity: 0.08, top: -80, right: -80 },
  safe:   { flex: 1 },
  content: { flex: 1, paddingHorizontal: 28, paddingTop: 20, paddingBottom: 40, alignItems: 'center' },

  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 48, alignSelf: 'flex-start' },
  brandMark: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 15, color: '#3D4A6B', letterSpacing: 1.5 },

  orbWrap: { marginBottom: 36 },

  greeting: {
    fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF',
    letterSpacing: -0.4, textAlign: 'center', marginBottom: 10,
  },
  sub: {
    fontSize: 14, color: '#6B7A9A', textAlign: 'center',
    lineHeight: 22, marginBottom: 28,
  },

  assurance: {
    backgroundColor: 'rgba(52,211,153,0.06)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.12)',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 9,
    marginBottom: 32,
  },
  assuranceText: { fontFamily: fonts.mono, fontSize: 10, color: '#3B6B52', textAlign: 'center' },

  actions: { width: '100%', gap: 10 },

  primaryBtn: {},
  primaryGrad: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  primaryText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },

  altBtn: { alignItems: 'center', paddingVertical: 14 },
  altText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: '#3D4A6B', textDecorationLine: 'underline' },
});
