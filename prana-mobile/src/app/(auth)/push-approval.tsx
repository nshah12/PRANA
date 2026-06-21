/**
 * Push approval screen — shown on the TRUSTED phone when a sign-in
 * is attempted from a NEW device/browser.
 *
 * Emotional job: "YOUR vault, YOUR decision. You control every door."
 *
 * This is NOT about fear — it's about power. The user is the gatekeeper.
 * The screen should feel authoritative and calm, not alarming.
 *
 * Flow:
 *   1. This phone receives a push notification while the session is live
 *   2. Polling GET /auth/employee/device/push-status?session_id=xxx
 *      until status = 'pending' → show details
 *   3. Approve: POST /auth/employee/device/push-approve { session_id }
 *      → the NEW device gets an access_token via its polling
 *   4. Deny:    POST /auth/employee/device/push-deny   { session_id }
 *      → the NEW device's session is invalidated
 *
 * The session_id is passed as a route param from the push notification handler.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, Animated, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

type RequestStatus = 'loading' | 'pending' | 'approved' | 'denied' | 'expired' | 'error';

interface LoginRequest {
  session_id: string;
  device_name: string;
  browser: string;
  location: string;
  ip_masked: string;
  requested_at: string;
  expires_at: string;
}

// ── Countdown timer ───────────────────────────────────────────────────────────
function ExpiryBar({ expiresAt }: { expiresAt: string }) {
  const [secsLeft, setSecsLeft] = useState(0);
  const progress = useRef(new Animated.Value(1)).current;
  const totalSecs = useRef(0);

  useEffect(() => {
    const expiry = new Date(expiresAt).getTime();
    const now = Date.now();
    const total = Math.max(1, Math.floor((expiry - now) / 1000));
    totalSecs.current = total;

    function tick() {
      const remaining = Math.max(0, Math.floor((expiry - Date.now()) / 1000));
      setSecsLeft(remaining);
      progress.setValue(remaining / total);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  const isUrgent = secsLeft < 30;
  const barColor = secsLeft < 15 ? colors.rose : isUrgent ? colors.amber : colors.emerald;
  const mins = Math.floor(secsLeft / 60);
  const secs = secsLeft % 60;
  const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  return (
    <View style={eb.wrap}>
      <View style={eb.track}>
        <Animated.View style={[eb.fill, { flex: progress as unknown as number, backgroundColor: barColor }]} />
        <Animated.View style={[eb.gap, { flex: Animated.subtract(1, progress) as unknown as number }]} />
      </View>
      <Text style={[eb.label, { color: barColor }]}>
        {secsLeft > 0 ? `Request expires in ${timeStr}` : 'Request has expired'}
      </Text>
    </View>
  );
}

const eb = StyleSheet.create({
  wrap: { marginVertical: 16 },
  track: { flexDirection: 'row', height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.06)', overflow: 'hidden', marginBottom: 6 },
  fill: { height: 3, borderRadius: 2 },
  gap: { height: 3 },
  label: { fontFamily: fonts.mono, fontSize: 10, textAlign: 'center' },
});

// ── Detail row ────────────────────────────────────────────────────────────────
function DetailRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={dr.row}>
      <Text style={dr.label}>{label}</Text>
      <Text style={[dr.value, highlight && dr.valueHighlight]}>{value}</Text>
    </View>
  );
}
const dr = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#5B6A8A' },
  value: { fontFamily: fonts.mono, fontSize: 12, color: '#C8D3E8' },
  valueHighlight: { color: colors.cyan },
});

// ── Screen ────────────────────────────────────────────────────────────────────
export default function PushApprovalScreen() {
  const { session_id } = useLocalSearchParams<{ session_id?: string }>();
  const [status,  setStatus]  = useState<RequestStatus>('loading');
  const [request, setRequest] = useState<LoginRequest | null>(null);
  const [error,   setError]   = useState('');
  const fadeIn  = useRef(new Animated.Value(0)).current;
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }).start();
    if (session_id) {
      loadRequest(session_id);
    } else {
      setStatus('error');
      setError('No login request found. This link may have expired.');
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [session_id]);

  async function loadRequest(sid: string) {
    try {
      const res = await api.get<{ status: string; request: LoginRequest }>(
        `/auth/employee/device/push-status?session_id=${sid}`,
      );
      if (res.status === 'pending') {
        setRequest(res.request);
        setStatus('pending');
        // Poll every 5s to catch expiry
        pollRef.current = setInterval(() => checkExpiry(res.request), 5000);
      } else if (res.status === 'expired') {
        setStatus('expired');
      } else {
        setStatus('error');
        setError('Unexpected request status.');
      }
    } catch {
      setStatus('error');
      setError('Couldn\'t load the login request. Check your connection.');
    }
  }

  function checkExpiry(req: LoginRequest) {
    if (new Date(req.expires_at).getTime() < Date.now()) {
      setStatus('expired');
      if (pollRef.current) clearInterval(pollRef.current);
    }
  }

  async function handleApprove() {
    if (!session_id) return;
    if (pollRef.current) clearInterval(pollRef.current);
    try {
      await api.post('/auth/employee/device/push-approve', { session_id });
      setStatus('approved');
    } catch {
      setError('Approval failed. Try again or deny the request.');
    }
  }

  async function handleDeny() {
    if (!session_id) return;
    if (pollRef.current) clearInterval(pollRef.current);
    try {
      await api.post('/auth/employee/device/push-deny', { session_id });
      setStatus('denied');
    } catch {
      setStatus('denied'); // deny optimistically — safer to assume denied
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

      <SafeAreaView style={s.safe}>
        <Animated.View style={[s.content, { opacity: fadeIn }]}>

          {/* Brand */}
          <View style={s.brandRow}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.brandMark}>
              <Text style={s.brandIcon}>P</Text>
            </LinearGradient>
            <Text style={s.brandName}>PRANA</Text>
          </View>

          {/* Loading */}
          {status === 'loading' && (
            <View style={s.centerState}>
              <ActivityIndicator size="large" color={colors.indigo} />
              <Text style={s.centerText}>Loading request…</Text>
            </View>
          )}

          {/* Pending — main action screen */}
          {status === 'pending' && request && (
            <>
              {/* Gate icon */}
              <View style={s.gateWrap}>
                <View style={s.gateOuter}>
                  <LinearGradient
                    colors={['rgba(251,191,36,0.15)', 'rgba(251,191,36,0.05)']}
                    style={s.gateGrad}
                  >
                    <Text style={s.gateEmoji}>🚨</Text>
                  </LinearGradient>
                </View>
              </View>

              {/* Framing — empowerment, not alarm */}
              <Text style={s.stepTag}>ACCESS REQUEST TO YOUR VAULT</Text>
              <Text style={s.title}>Someone wants in.</Text>
              <Text style={s.sub}>
                A sign-in attempt was made on a different device. Only you can approve it. If this wasn't you, deny it immediately.
              </Text>

              {/* Expiry countdown */}
              <ExpiryBar expiresAt={request.expires_at} />

              {/* Request details */}
              <View style={s.detailCard}>
                <DetailRow label="Device / Browser" value={request.browser || request.device_name} highlight />
                <DetailRow label="Location" value={request.location} />
                <DetailRow label="IP Address" value={request.ip_masked} />
                <DetailRow label="Requested at" value={new Date(request.requested_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} />
              </View>

              {/* Safety note */}
              <View style={s.safetyNote}>
                <Text style={s.safetyText}>🛡️  PRANA will never send you approval requests over email or SMS. Only trust this in-app notification.</Text>
              </View>

              {error ? (
                <View style={s.errorBox}><Text style={s.errorText}>{error}</Text></View>
              ) : null}

              {/* Deny / Approve */}
              <View style={s.btnRow}>
                <Pressable onPress={handleDeny} style={({ pressed }) => [s.denyBtn, pressed && { opacity: 0.8 }]}>
                  <Text style={s.denyText}>Not me — Deny</Text>
                </Pressable>
                <Pressable onPress={handleApprove} style={({ pressed }) => [s.approveWrap, pressed && { opacity: 0.85 }]}>
                  <LinearGradient
                    colors={gradJourney.colors}
                    locations={gradJourney.locations}
                    start={gradJourney.start}
                    end={gradJourney.end}
                    style={s.approveBtn}
                  >
                    <Text style={s.approveText}>Yes, it's me →</Text>
                  </LinearGradient>
                </Pressable>
              </View>
            </>
          )}

          {/* Approved */}
          {status === 'approved' && (
            <View style={s.outcomeWrap}>
              <LinearGradient colors={['#34D399', '#22D3EE']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.outcomeCircle}>
                <Text style={s.outcomeTick}>✓</Text>
              </LinearGradient>
              <Text style={s.outcomeTitle}>Access approved</Text>
              <Text style={s.outcomeSub}>The other device can now access your vault. You'll see this session in your activity log.</Text>
              <Pressable onPress={() => router.replace('/(vault)/vault')} style={s.outcomeBack}>
                <Text style={s.outcomeBackText}>Back to my vault →</Text>
              </Pressable>
            </View>
          )}

          {/* Denied */}
          {status === 'denied' && (
            <View style={s.outcomeWrap}>
              <View style={[s.outcomeCircle, { backgroundColor: 'rgba(251,113,133,0.2)' }]}>
                <Text style={s.outcomeTick}>✕</Text>
              </View>
              <Text style={s.outcomeTitle}>Access denied</Text>
              <Text style={s.outcomeSub}>The request has been blocked. If you didn't initiate this, consider changing your OTP method from Settings.</Text>
              <Pressable onPress={() => router.replace('/(vault)/vault')} style={s.outcomeBack}>
                <Text style={s.outcomeBackText}>Back to my vault →</Text>
              </Pressable>
            </View>
          )}

          {/* Expired */}
          {status === 'expired' && (
            <View style={s.outcomeWrap}>
              <View style={[s.outcomeCircle, { backgroundColor: 'rgba(251,191,36,0.15)' }]}>
                <Text style={[s.outcomeTick, { color: colors.amber }]}>⏱</Text>
              </View>
              <Text style={s.outcomeTitle}>Request expired</Text>
              <Text style={s.outcomeSub}>The login request timed out. The other device will need to try signing in again.</Text>
              <Pressable onPress={() => router.replace('/(vault)/vault')} style={s.outcomeBack}>
                <Text style={s.outcomeBackText}>Back to my vault →</Text>
              </Pressable>
            </View>
          )}

          {/* Error */}
          {status === 'error' && (
            <View style={s.outcomeWrap}>
              <View style={[s.outcomeCircle, { backgroundColor: 'rgba(251,113,133,0.15)' }]}>
                <Text style={s.outcomeTick}>!</Text>
              </View>
              <Text style={s.outcomeTitle}>Something went wrong</Text>
              <Text style={s.outcomeSub}>{error || 'Couldn\'t load the request. Try again.'}</Text>
              <Pressable onPress={() => router.replace('/(vault)/vault')} style={s.outcomeBack}>
                <Text style={s.outcomeBackText}>Back to my vault →</Text>
              </Pressable>
            </View>
          )}
        </Animated.View>
      </SafeAreaView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1 },
  orbTR: { position: 'absolute', width: 240, height: 240, borderRadius: 120, backgroundColor: colors.amber, opacity: 0.04, top: -80, right: -80 },
  safe: { flex: 1 },
  content: { flex: 1, paddingHorizontal: 28, paddingTop: 20, paddingBottom: 40 },

  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 28 },
  brandMark: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 13, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 13, color: '#3D4A6B', letterSpacing: 1.5 },

  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16 },
  centerText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: '#5B6A8A' },

  gateWrap: { alignItems: 'center', marginBottom: 20 },
  gateOuter: { width: 90, height: 90, borderRadius: 28, overflow: 'hidden' },
  gateGrad: { flex: 1, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(251,191,36,0.3)', borderRadius: 28 },
  gateEmoji: { fontSize: 38 },

  stepTag: { fontFamily: fonts.mono, fontSize: 9, color: colors.amber, letterSpacing: 1.5, marginBottom: 8 },
  title: { fontFamily: fonts.displayBold, fontSize: 26, color: '#FFFFFF', letterSpacing: -0.4, marginBottom: 8 },
  sub: { fontSize: 13, color: '#6B7A9A', lineHeight: 21, marginBottom: 4 },

  detailCard: {
    backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)', borderRadius: 16, paddingHorizontal: 16, marginBottom: 14,
  },

  safetyNote: {
    backgroundColor: 'rgba(52,211,153,0.06)', borderWidth: 1, borderColor: 'rgba(52,211,153,0.12)',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, marginBottom: 16,
  },
  safetyText: { fontFamily: fonts.mono, fontSize: 10, color: '#3B6B52', lineHeight: 16 },

  errorBox: {
    backgroundColor: 'rgba(251,113,133,0.10)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.20)',
    borderRadius: 12, padding: 12, marginBottom: 12,
  },
  errorText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#FCA5A5', textAlign: 'center' },

  btnRow: { flexDirection: 'row', gap: 10, marginTop: 'auto' },
  denyBtn: {
    flex: 1, backgroundColor: 'rgba(251,113,133,0.10)',
    borderWidth: 1, borderColor: 'rgba(251,113,133,0.25)',
    borderRadius: 16, alignItems: 'center', justifyContent: 'center', height: 56,
  },
  denyText: { fontFamily: fonts.displayBold, fontSize: 14, color: '#FCA5A5' },
  approveWrap: { flex: 2 },
  approveBtn: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  approveText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },

  outcomeWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, paddingHorizontal: 16 },
  outcomeCircle: { width: 80, height: 80, borderRadius: 40, alignItems: 'center', justifyContent: 'center' },
  outcomeTick: { fontSize: 34, color: '#04261C', fontWeight: '700' },
  outcomeTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF', letterSpacing: -0.3, textAlign: 'center' },
  outcomeSub: { fontSize: 13, color: '#6B7A9A', lineHeight: 21, textAlign: 'center' },
  outcomeBack: { marginTop: 8 },
  outcomeBackText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo, textDecorationLine: 'underline' },
});
