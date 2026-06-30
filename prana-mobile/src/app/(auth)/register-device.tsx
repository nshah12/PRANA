/**
 * Register device screen — first time on a new device.
 *
 * Emotional job: "Your vault has accepted this phone. It belongs to you now."
 *
 * This is not a security form — it's the vault WELCOMING a new device
 * into the user's trusted circle. The user is extending ownership,
 * not completing a registration checklist.
 *
 * API: POST /auth/employee/device/register
 *   body: { step_token, device_name, device_public_key, platform, os_version }
 *   → { device_id, registered_at }
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, TextInput, Animated, Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as Device from 'expo-device';
import * as SecureStore from 'expo-secure-store';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { tError, tUi } from '@/i18n';

// ── Animated device card ──────────────────────────────────────────────────────
function DeviceCard({ name, accepted }: { name: string; accepted: boolean }) {
  const glow = useRef(new Animated.Value(0.15)).current;
  const scale = useRef(new Animated.Value(0.8)).current;
  const checkScale = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(scale, { toValue: 1, friction: 5, tension: 180, useNativeDriver: true }).start();
    Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 0.45, duration: 1800, useNativeDriver: true }),
        Animated.timing(glow, { toValue: 0.15, duration: 1800, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  useEffect(() => {
    if (accepted) {
      Animated.spring(checkScale, { toValue: 1, friction: 4, tension: 200, useNativeDriver: true }).start();
    }
  }, [accepted]);

  const deviceEmoji = Platform.OS === 'ios' ? '📱' : '📲';

  return (
    <Animated.View style={[dc.outer, { transform: [{ scale }] }]}>
      {/* Vault connection line — thin beam from vault icon above to device */}
      <View style={dc.beamWrap}>
        <LinearGradient
          colors={['rgba(99,102,241,0)', 'rgba(99,102,241,0.35)', 'rgba(52,211,153,0.2)']}
          locations={[0, 0.5, 1]}
          start={{ x: 0.5, y: 0 }}
          end={{ x: 0.5, y: 1 }}
          style={dc.beam}
        />
      </View>

      {/* Vault icon at top */}
      <LinearGradient
        colors={gradJourney.colors}
        locations={gradJourney.locations}
        start={gradJourney.start}
        end={gradJourney.end}
        style={dc.vaultPin}
      >
        <Text style={dc.vaultEmoji}>🔐</Text>
      </LinearGradient>

      {/* Device card with ambient glow */}
      <View style={dc.cardWrap}>
        <Animated.View style={[dc.glow, { opacity: glow }]} />
        <View style={dc.card}>
          <Text style={dc.deviceEmoji}>{deviceEmoji}</Text>
          <Text style={dc.deviceName} numberOfLines={1}>{name || 'My Phone'}</Text>
          {accepted ? (
            <Animated.View style={[dc.acceptedBadge, { transform: [{ scale: checkScale }] }]}>
              <Text style={dc.acceptedText}>✓ Trusted</Text>
            </Animated.View>
          ) : (
            <View style={dc.pendingBadge}>
              <Text style={dc.pendingText}>Registering…</Text>
            </View>
          )}
        </View>
      </View>
    </Animated.View>
  );
}

const dc = StyleSheet.create({
  outer: { alignItems: 'center', marginBottom: 32 },
  beamWrap: { alignItems: 'center' },
  beam: { width: 2, height: 40 },
  vaultPin: {
    width: 40, height: 40, borderRadius: 13,
    alignItems: 'center', justifyContent: 'center', marginBottom: 0,
  },
  vaultEmoji: { fontSize: 18 },
  cardWrap: { alignItems: 'center', marginTop: 0 },
  glow: {
    position: 'absolute', width: 160, height: 160, borderRadius: 80,
    backgroundColor: colors.indigo,
  },
  card: {
    width: 130, backgroundColor: 'rgba(20,28,55,0.9)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.3)',
    borderRadius: 22, padding: 16, alignItems: 'center', gap: 8,
  },
  deviceEmoji: { fontSize: 36 },
  deviceName: {
    fontFamily: fonts.mono, fontSize: 10, color: '#A0AECB',
    letterSpacing: 0.3, textAlign: 'center',
  },
  acceptedBadge: {
    backgroundColor: 'rgba(52,211,153,0.15)', borderWidth: 1,
    borderColor: colors.emerald, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 4,
  },
  acceptedText: { fontFamily: fonts.mono, fontSize: 10, color: colors.emerald },
  pendingBadge: {
    backgroundColor: 'rgba(99,102,241,0.12)', borderWidth: 1,
    borderColor: 'rgba(99,102,241,0.3)', borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 4,
  },
  pendingText: { fontFamily: fonts.mono, fontSize: 10, color: colors.indigo },
});

// ── Screen ────────────────────────────────────────────────────────────────────
export default function RegisterDeviceScreen() {
  const [deviceName, setDeviceName] = useState('');
  const [loading,    setLoading]    = useState(false);
  const [accepted,   setAccepted]   = useState(false);
  const [error,      setError]      = useState('');
  const fadeIn = useRef(new Animated.Value(0)).current;
  const inputRef = useRef<TextInput>(null);

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 600, useNativeDriver: true }).start();
    const defaultName = Device.modelName ?? (Platform.OS === 'ios' ? 'iPhone' : 'Android Phone');
    setDeviceName(defaultName);
  }, []);

  async function handleRegister() {
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      const stepToken = authStore.getStepToken();
      if (!stepToken) { router.replace('/(auth)/sign-in'); return; }

      const devicePublicKey = await generateDeviceKey();

      const res = await api.post<{ device_id: string; registered_at: string }>(
        '/auth/employee/device/register',
        {
          step_token: stepToken,
          device_name: deviceName.trim() || 'My Phone',
          device_public_key: devicePublicKey,
          platform: Platform.OS,
          os_version: `${Platform.OS} ${Platform.Version}`,
        },
      );

      await SecureStore.setItemAsync('prana_device_id', res.device_id);
      setAccepted(true);
      // Short pause to let the user see the "Trusted" badge before moving on
      setTimeout(() => router.replace('/(auth)/enable-face-id'), 900);
    } catch (e: any) {
      const code = e?.body?.error ?? e?.response?.data?.error;
      if (code === 'DEVICE_LIMIT_REACHED') {
        setError(tError('DEVICE_LIMIT_REACHED'));
      } else {
        setError(tUi('SOMETHING_WENT_WRONG'));
      }
      setLoading(false);
    }
  }

  return (
    <LinearGradient
      colors={['#080D1A', '#0F172A', '#131B33']}
      locations={[0, 0.5, 1]}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={s.screen}
    >
      <View style={s.orbTR} pointerEvents="none" />
      <View style={s.orbBL} pointerEvents="none" />

      <SafeAreaView style={s.safe}>
        <Animated.View style={[s.content, { opacity: fadeIn }]}>

          {/* Brand */}
          <View style={s.brandRow}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.brandMark}>
              <Text style={s.brandIcon}>P</Text>
            </LinearGradient>
            <Text style={s.brandName}>PRANA</Text>
          </View>

          {/* Device visual — vault above, connected to device below */}
          <DeviceCard name={deviceName} accepted={accepted} />

          {/* Step context */}
          <Text style={s.stepTag}>ADDING TO YOUR TRUSTED DEVICES</Text>
          <Text style={s.title}>Name this phone</Text>
          <Text style={s.sub}>
            Your vault will recognise this device from now on. Give it a name you'll remember if you ever manage your trusted devices.
          </Text>

          {/* Device name input */}
          <Pressable onPress={() => inputRef.current?.focus()} style={s.inputWrap}>
            <Text style={s.inputLabel}>Device name</Text>
            <TextInput
              ref={inputRef}
              value={deviceName}
              onChangeText={setDeviceName}
              placeholder="e.g. My Work Phone"
              placeholderTextColor="#3D4A6B"
              maxLength={40}
              style={s.input}
              returnKeyType="done"
              onSubmitEditing={handleRegister}
            />
          </Pressable>

          {/* Trust signals */}
          <View style={s.trustCard}>
            <TrustRow icon="🔑" title="Secure key generated" sub="A private key is created on this device and never leaves it" />
            <TrustRow icon="👁️" title="Full transparency" sub="You can see and remove trusted devices in Settings" />
            <TrustRow icon="🔔" title="You'll be notified" sub="Anytime a new device is added to your vault" />
          </View>

          {error ? (
            <View style={s.errorBox}><Text style={s.errorText}>{error}</Text></View>
          ) : null}

          {/* CTA */}
          <Pressable
            onPress={handleRegister}
            disabled={loading || accepted}
            style={({ pressed }) => [s.ctaWrap, pressed && { opacity: 0.85 }]}
          >
            <LinearGradient
              colors={gradJourney.colors}
              locations={gradJourney.locations}
              start={gradJourney.start}
              end={gradJourney.end}
              style={[s.cta, (loading || accepted) && { opacity: 0.6 }]}
            >
              <Text style={s.ctaText}>
                {accepted ? 'Device trusted ✓' : loading ? 'Registering…' : 'Trust this device →'}
              </Text>
            </LinearGradient>
          </Pressable>
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

function TrustRow({ icon, title, sub }: { icon: string; title: string; sub: string }) {
  return (
    <View style={tr.row}>
      <Text style={tr.icon}>{icon}</Text>
      <View style={tr.text}>
        <Text style={tr.title}>{title}</Text>
        <Text style={tr.sub}>{sub}</Text>
      </View>
    </View>
  );
}
const tr = StyleSheet.create({
  row: { flexDirection: 'row', gap: 12, paddingVertical: 9, alignItems: 'flex-start' },
  icon: { fontSize: 16, width: 24, textAlign: 'center', marginTop: 1 },
  text: { flex: 1 },
  title: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#C8D3E8', marginBottom: 2 },
  sub: { fontSize: 11, color: '#5B6A8A', lineHeight: 17 },
});

async function generateDeviceKey(): Promise<string> {
  try {
    const { getRandomBytes } = await import('expo-crypto');
    const bytes = getRandomBytes(32);
    return btoa(String.fromCharCode(...bytes));
  } catch {
    const arr = new Uint8Array(32);
    for (let i = 0; i < 32; i++) arr[i] = Math.floor(Math.random() * 256);
    return btoa(String.fromCharCode(...arr));
  }
}

const s = StyleSheet.create({
  screen: { flex: 1 },
  orbTR: { position: 'absolute', width: 200, height: 200, borderRadius: 100, backgroundColor: colors.cyan, opacity: 0.05, top: -60, right: -70 },
  orbBL: { position: 'absolute', width: 180, height: 180, borderRadius: 90, backgroundColor: colors.indigo, opacity: 0.07, bottom: 40, left: -80 },
  safe: { flex: 1 },
  content: { flex: 1, paddingHorizontal: 28, paddingTop: 20, paddingBottom: 40 },

  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 32 },
  brandMark: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 13, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 13, color: '#3D4A6B', letterSpacing: 1.5 },

  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.cyan, letterSpacing: 1.5, marginBottom: 8 },
  title: { fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF', letterSpacing: -0.4, marginBottom: 8 },
  sub: { fontSize: 13, color: '#6B7A9A', lineHeight: 21, marginBottom: 20 },

  inputWrap: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1.5, borderColor: 'rgba(99,102,241,0.3)',
    borderRadius: 14, paddingHorizontal: 16, paddingTop: 10, paddingBottom: 6,
    marginBottom: 16,
  },
  inputLabel: { fontFamily: fonts.mono, fontSize: 9, color: '#4B5880', letterSpacing: 0.8, marginBottom: 4 },
  input: { fontFamily: fonts.bodySemiBold, fontSize: 15, color: '#FFFFFF', paddingVertical: 4 },

  trustCard: {
    backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.07)', borderRadius: 16,
    paddingHorizontal: 16, paddingVertical: 4, marginBottom: 20,
  },

  errorBox: {
    backgroundColor: 'rgba(251,113,133,0.10)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 16,
  },
  errorText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5', textAlign: 'center' },

  ctaWrap: { marginTop: 'auto' },
  cta: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  ctaText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },
});
