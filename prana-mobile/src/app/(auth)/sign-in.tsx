/**
 * Sign-in screen — the homecoming screen.
 *
 * Emotional job: "Your vault is waiting. It's been keeping everything safe.
 * Let's just make sure it's you."
 *
 * Design decisions:
 * - No feature list, no marketing — the user already chose PRANA.
 *   Just open the door.
 * - Vault icon at top (pulsing gently) = "it's here, it's yours"
 * - Single field, no distractions
 * - Trust signals are inline facts, not a footer
 * - Error handling is kind, not punishing
 * - CTA says "Open my vault →" not "Send OTP" — it's THEIRS
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, StyleSheet, Pressable,
  ActivityIndicator, Animated, Easing, KeyboardAvoidingView, Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, gradJourney, radius } from '@/prana-theme/tokens';

function PulsingVault() {
  const pulse  = useRef(new Animated.Value(1)).current;
  const glow   = useRef(new Animated.Value(0.3)).current;
  const appear = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(appear, { toValue: 1, friction: 5, tension: 180, useNativeDriver: true }).start();
    Animated.loop(
      Animated.sequence([
        Animated.parallel([
          Animated.timing(pulse, { toValue: 1.07, duration: 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(glow,  { toValue: 0.6,  duration: 1600, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(pulse, { toValue: 1.00, duration: 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(glow,  { toValue: 0.3,  duration: 1600, useNativeDriver: true }),
        ]),
      ])
    ).start();
  }, []);

  return (
    <Animated.View style={[vault.wrap, { transform: [{ scale: appear }] }]}>
      <Animated.View style={[vault.glow, { opacity: glow, transform: [{ scale: pulse }] }]} />
      <Animated.View style={[vault.box, { transform: [{ scale: pulse }] }]}>
        <LinearGradient
          colors={gradJourney.colors}
          locations={gradJourney.locations}
          start={gradJourney.start}
          end={gradJourney.end}
          style={vault.grad}
        >
          <Text style={vault.emoji}>🔐</Text>
        </LinearGradient>
      </Animated.View>
    </Animated.View>
  );
}

const vault = StyleSheet.create({
  wrap:  { alignItems: 'center', marginBottom: 28, marginTop: 8 },
  glow:  { position: 'absolute', width: 110, height: 110, borderRadius: 55, backgroundColor: colors.indigo },
  box:   {},
  grad:  { width: 76, height: 76, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  emoji: { fontSize: 34 },
});

export default function SignInScreen() {
  const [mobile,   setMobile]   = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [cooldown, setCooldown] = useState(0);
  const inputRef  = useRef<TextInput>(null);
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const fadeIn    = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 700, useNativeDriver: true }).start();
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown(v => v <= 1 ? 0 : v - 1), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  function shake() {
    shakeAnim.setValue(0);
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 9,  duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -9, duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 5,  duration: 55, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0,  duration: 55, useNativeDriver: true }),
    ]).start();
  }

  async function handleContinue() {
    const cleaned = mobile.replace(/\D/g, '');
    if (cleaned.length < 10) {
      setError('Enter your 10-digit mobile number registered with PRANA.');
      shake();
      return;
    }
    if (cooldown > 0) return;
    setError('');
    setLoading(true);
    try {
      await api.post('/auth/employee/request-otp', { mobile: cleaned });
      authStore.setPendingMobile(cleaned);
      router.push('/(auth)/otp-verify');
    } catch (e: any) {
      const code = e?.body?.error ?? e?.response?.data?.error;
      if (code === 'RATE_LIMITED') {
        setCooldown(60);
        setError('Too many attempts. Your vault will be accessible again in 60 seconds.');
      } else if (code === 'MOBILE_NOT_REGISTERED') {
        setError('This number isn\'t linked to a PRANA vault yet. Your employer needs to add you first.');
      } else {
        setError('Something went wrong. Check your connection and try again.');
      }
      shake();
    } finally {
      setLoading(false);
    }
  }

  // Format as  98765 43210  while typing
  const digits    = mobile.replace(/\D/g, '').slice(0, 10);
  const formatted = digits.length > 5 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits;
  const isReady   = digits.length === 10;

  return (
    <LinearGradient
      colors={['#080D1A', '#0F172A', '#131B33']}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={s.screen}
    >
      {/* Ambient orbs */}
      <View style={s.orbTL} pointerEvents="none" />
      <View style={s.orbBR} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <Animated.ScrollView
            style={{ flex: 1, opacity: fadeIn }}
            contentContainerStyle={s.scroll}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            {/* Brand */}
            <View style={s.brandRow}>
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.brandMark}>
                <Text style={s.brandIcon}>P</Text>
              </LinearGradient>
              <Text style={s.brandName}>PRANA</Text>
            </View>

            {/* Pulsing vault — "it's here, it's yours" */}
            <PulsingVault />

            {/* Headline */}
            <Text style={s.headline}>Welcome back.</Text>
            <Text style={s.subhead}>
              Your vault has been keeping everything safe.{'\n'}
              Let's confirm it's you.
            </Text>

            {/* Form card */}
            <Animated.View style={[s.card, { transform: [{ translateX: shakeAnim }] }]}>

              {/* Step indicator */}
              <View style={s.stepRow}>
                <View style={[s.stepDot, s.stepDotActive]} />
                <View style={s.stepLine} />
                <View style={s.stepDot} />
                <View style={s.stepLine} />
                <View style={s.stepDot} />
              </View>
              <Text style={s.stepHint}>Step 1 of 3 — Mobile verification</Text>

              {/* Field */}
              <View style={s.fieldGroup}>
                <Text style={s.fieldLabel}>REGISTERED MOBILE</Text>
                <Pressable onPress={() => inputRef.current?.focus()}>
                  <View style={[s.fieldRow, error ? s.fieldRowError : isReady ? s.fieldRowReady : {}]}>
                    <Text style={s.countryFlag}>🇮🇳</Text>
                    <Text style={s.countryCode}>+91</Text>
                    <View style={s.divider} />
                    <TextInput
                      ref={inputRef}
                      style={s.input}
                      placeholder="98765 43210"
                      placeholderTextColor="#3D4A6B"
                      keyboardType="phone-pad"
                      value={formatted}
                      onChangeText={v => {
                        setMobile(v.replace(/\D/g, ''));
                        setError('');
                      }}
                      editable={!loading}
                      maxLength={11}
                      returnKeyType="done"
                      onSubmitEditing={handleContinue}
                    />
                    {isReady && !error && (
                      <View style={s.readyTick}>
                        <Text style={s.readyTickText}>✓</Text>
                      </View>
                    )}
                  </View>
                </Pressable>
                {error ? (
                  <View style={s.errorRow}>
                    <Text style={s.errorIcon}>⚠</Text>
                    <Text style={s.errorText}>{error}</Text>
                  </View>
                ) : null}
              </View>
            </Animated.View>

            {/* CTA */}
            {loading ? (
              <View style={s.loadingRow}>
                <ActivityIndicator color={colors.emerald} />
                <Text style={s.loadingText}>Sending a code to your phone…</Text>
              </View>
            ) : cooldown > 0 ? (
              <View style={s.cooldownPill}>
                <Text style={s.cooldownText}>⏳  Try again in {cooldown}s</Text>
              </View>
            ) : (
              <Pressable
                onPress={handleContinue}
                style={({ pressed }) => [s.ctaWrap, pressed && { opacity: 0.85 }]}
              >
                <LinearGradient
                  colors={gradJourney.colors}
                  locations={gradJourney.locations}
                  start={gradJourney.start}
                  end={gradJourney.end}
                  style={s.cta}
                >
                  <Text style={s.ctaText}>Open my vault  →</Text>
                </LinearGradient>
              </Pressable>
            )}

            {/* Push approval alt */}
            <Pressable onPress={() => router.push('/(auth)/push-approval')} style={s.altRow}>
              <Text style={s.altText}>Approve on a trusted device instead</Text>
            </Pressable>

            {/* Trust trinity — NOT a footer, part of the experience */}
            <View style={s.trustCard}>
              <TrustItem icon="🔐" heading="End-to-end encrypted" body="AES-256 per employee. Your employer can push, never pull." />
              <View style={s.trustDivider} />
              <TrustItem icon="🇮🇳" heading="Data stays in India" body="Mumbai + Hyderabad regions. DPDP Act 2023 compliant." />
              <View style={s.trustDivider} />
              <TrustItem icon="👤" heading="Only you can open it" body="No PRANA staff, no employer, no third party — just you." />
            </View>
          </Animated.ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </LinearGradient>
  );
}

function TrustItem({ icon, heading, body }: { icon: string; heading: string; body: string }) {
  return (
    <View style={ti.wrap}>
      <Text style={ti.icon}>{icon}</Text>
      <View style={{ flex: 1 }}>
        <Text style={ti.heading}>{heading}</Text>
        <Text style={ti.body}>{body}</Text>
      </View>
    </View>
  );
}

const ti = StyleSheet.create({
  wrap:    { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 10 },
  icon:    { fontSize: 18, marginTop: 1 },
  heading: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#CBD5E1', marginBottom: 1 },
  body:    { fontFamily: fonts.bodyRegular, fontSize: 11, color: '#4B5A78', lineHeight: 16 },
});

const s = StyleSheet.create({
  screen: { flex: 1 },
  orbTL: {
    position: 'absolute', width: 260, height: 260, borderRadius: 130,
    backgroundColor: colors.indigo, opacity: 0.07,
    top: -80, left: -100,
  },
  orbBR: {
    position: 'absolute', width: 200, height: 200, borderRadius: 100,
    backgroundColor: colors.emerald, opacity: 0.05,
    bottom: 40, right: -80,
  },
  safe: { flex: 1 },
  scroll: { paddingHorizontal: 24, paddingTop: 16, paddingBottom: 48 },

  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 24 },
  brandMark: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 15, color: '#3D4A6B', letterSpacing: 1.5 },

  headline: {
    fontFamily: fonts.displayBold, fontSize: 28, color: '#FFFFFF',
    letterSpacing: -0.5, marginBottom: 8,
  },
  subhead: {
    fontSize: 14, color: '#6B7A9A', lineHeight: 22, marginBottom: 24,
  },

  card: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)',
    borderRadius: 22, padding: 18, marginBottom: 14,
  },

  stepRow:    { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  stepDot:    { width: 8, height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.12)' },
  stepDotActive: { backgroundColor: colors.emerald },
  stepLine:   { flex: 1, height: 1.5, backgroundColor: 'rgba(255,255,255,0.07)', marginHorizontal: 3 },
  stepHint:   { fontFamily: fonts.mono, fontSize: 9, color: '#4B5A78', letterSpacing: 1, marginBottom: 16 },

  fieldGroup: {},
  fieldLabel: { fontFamily: fonts.mono, fontSize: 9, color: '#4B5A78', letterSpacing: 1.2, marginBottom: 7 },
  fieldRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.09)',
    borderRadius: radius.md, height: 54, paddingHorizontal: 14,
  },
  fieldRowReady: { borderColor: 'rgba(52,211,153,0.4)' },
  fieldRowError: { borderColor: 'rgba(251,113,133,0.5)' },
  countryFlag:   { fontSize: 16, marginRight: 6 },
  countryCode:   { fontFamily: fonts.mono, fontSize: 13, color: '#6B7A9A', marginRight: 8 },
  divider:       { width: 1, height: 20, backgroundColor: 'rgba(255,255,255,0.10)', marginRight: 10 },
  input: {
    flex: 1, fontFamily: fonts.mono, fontSize: 17,
    color: '#FFFFFF', letterSpacing: 1.5,
  },
  readyTick: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: 'rgba(52,211,153,0.15)',
    alignItems: 'center', justifyContent: 'center',
  },
  readyTickText: { fontSize: 12, color: colors.emerald, fontWeight: '700' },

  errorRow: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', marginTop: 8 },
  errorIcon: { fontSize: 12, color: colors.rose, marginTop: 1 },
  errorText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 11, color: '#FCA5A5', lineHeight: 17 },

  loadingRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10, height: 56, marginBottom: 10,
  },
  loadingText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.emerald },

  cooldownPill: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.07)',
    borderRadius: 16, height: 56,
    alignItems: 'center', justifyContent: 'center', marginBottom: 10,
  },
  cooldownText: { fontFamily: fonts.mono, fontSize: 13, color: '#4B5A78' },

  ctaWrap: { marginBottom: 10 },
  cta: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  ctaText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C', letterSpacing: -0.2 },

  altRow: { alignItems: 'center', paddingVertical: 14, marginBottom: 20 },
  altText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#3D4A6B', textDecorationLine: 'underline' },

  trustCard: {
    backgroundColor: 'rgba(255,255,255,0.025)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)',
    borderRadius: 18, paddingHorizontal: 16, paddingVertical: 4,
  },
  trustDivider: { height: 1, backgroundColor: 'rgba(255,255,255,0.05)' },
});
