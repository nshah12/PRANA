/**
 * Shares screen — all active and expired share links.
 *
 * Emotional job: "You control every door out of your vault."
 * Share links are time-limited and revocable. This screen makes
 * that control tangible — the employee sees exactly who can see
 * what, and can cut access with one tap.
 *
 * API:
 *   GET    /vault/shares              → { shares: ShareLink[] }
 *   DELETE /vault/shares/{token_id}   → 204
 */
import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, Modal, Alert, TouchableWithoutFeedback,
} from 'react-native';
import { tUi } from '@/i18n';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { useShares, type ShareLink } from '@/hooks/useVault';
import { api } from '@/lib/api';

// ── Expiry helpers ────────────────────────────────────────────────────────────

function formatExpiry(expires_at: string | null): string {
  if (!expires_at) return 'Never expires';
  const d = new Date(expires_at);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  if (diffMs < 0) return 'Expired';
  const diffH = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffH < 24) return `Expires in ${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  return `Expires ${d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}`;
}

function isExpired(expires_at: string | null): boolean {
  if (!expires_at) return false;
  return new Date(expires_at).getTime() < Date.now();
}

// ── Revoke confirm sheet ──────────────────────────────────────────────────────

function RevokeSheet({
  share, onConfirm, onCancel, loading,
}: { share: ShareLink; onConfirm: () => void; onCancel: () => void; loading: boolean }) {
  return (
    <Modal transparent animationType="slide" onRequestClose={onCancel}>
      <TouchableWithoutFeedback onPress={onCancel}>
        <View style={rs.overlay}>
          <View style={rs.panel}>
          <View style={rs.handle} />
          <View style={rs.warningIcon}>
            <Text style={rs.warningEmoji}>⚠</Text>
          </View>
          <Text style={rs.title}>Revoke access?</Text>
          <Text style={rs.sub}>
            The link for <Text style={rs.bold}>{share.label || 'this document'}</Text> will stop working immediately. Anyone who has it will lose access.
          </Text>
          <View style={rs.usageRow}>
            <Text style={rs.usageText}>
              Used {share.usage_count} time{share.usage_count === 1 ? '' : 's'}
              {share.usage_limit ? ` of ${share.usage_limit}` : ''}
            </Text>
          </View>
          <Pressable
            onPress={onConfirm}
            disabled={loading}
            style={[rs.revokeBtn, loading && { opacity: 0.6 }]}
          >
            {loading
              ? <ActivityIndicator size="small" color="#FFFFFF" />
              : <Text style={rs.revokeBtnText}>Yes, revoke access</Text>
            }
          </Pressable>
          <Pressable style={rs.cancelBtn} onPress={onCancel}>
            <Text style={rs.cancelText}>Keep it active</Text>
          </Pressable>
          </View>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}
const rs = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  panel: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 22, paddingBottom: 36 },
  handle: { width: 36, height: 4, backgroundColor: colors.surface3, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  warningIcon: { width: 54, height: 54, borderRadius: 27, backgroundColor: 'rgba(251,113,133,0.12)', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: 14 },
  warningEmoji: { fontSize: 24 },
  title: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.ink, textAlign: 'center', marginBottom: 8 },
  sub: { fontSize: 13, color: colors.ink2, lineHeight: 21, textAlign: 'center', marginBottom: 14 },
  bold: { fontFamily: fonts.bodySemiBold, color: colors.ink },
  usageRow: { backgroundColor: colors.surface3, borderRadius: 10, padding: 10, marginBottom: 20 },
  usageText: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3, textAlign: 'center' },
  revokeBtn: { backgroundColor: '#E11D48', borderRadius: 16, height: 52, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  revokeBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#FFFFFF' },
  cancelBtn: { alignItems: 'center', paddingVertical: 12 },
  cancelText: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink3 },
});

// ── Share card ────────────────────────────────────────────────────────────────

function ShareCard({
  share, onRevoke,
}: { share: ShareLink; onRevoke: (s: ShareLink) => void }) {
  const expired = isExpired(share.expires_at);
  const expiryStr = formatExpiry(share.expires_at);
  const usagePct = share.usage_limit
    ? Math.min(1, share.usage_count / share.usage_limit)
    : null;

  return (
    <View style={[sc.card, expired && sc.cardExpired]}>
      {/* Header row */}
      <View style={sc.topRow}>
        <View style={sc.iconWrap}>
          <Text style={sc.icon}>↗</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={sc.label} numberOfLines={1}>
            {share.label || 'Shared document'}
          </Text>
          <Text style={sc.created}>
            Created {new Date(share.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
          </Text>
        </View>
        <View style={[sc.statusBadge, expired ? sc.statusExpired : sc.statusActive]}>
          <Text style={[sc.statusText, expired ? sc.statusTextExpired : sc.statusTextActive]}>
            {expired ? 'EXPIRED' : 'ACTIVE'}
          </Text>
        </View>
      </View>

      {/* Expiry + usage */}
      <View style={sc.metaRow}>
        <View style={sc.metaItem}>
          <Text style={sc.metaIcon}>⏱</Text>
          <Text style={[sc.metaText, expired && { color: colors.rose }]}>{expiryStr}</Text>
        </View>
        <View style={sc.metaDot} />
        <View style={sc.metaItem}>
          <Text style={sc.metaIcon}>👁</Text>
          <Text style={sc.metaText}>
            Viewed {share.usage_count} time{share.usage_count === 1 ? '' : 's'}
            {share.usage_limit ? ` / ${share.usage_limit} max` : ''}
          </Text>
        </View>
      </View>

      {/* Usage bar when limit set */}
      {usagePct !== null && (
        <View style={sc.usageBarWrap}>
          <View style={[sc.usageBar, { width: `${Math.round(usagePct * 100)}%` as any }]} />
        </View>
      )}

      {/* Revoke */}
      {!expired && (
        <Pressable style={sc.revokeBtn} onPress={() => onRevoke(share)}>
          <Text style={sc.revokeBtnText}>✕  Revoke access</Text>
        </Pressable>
      )}
    </View>
  );
}

const sc = StyleSheet.create({
  card: { backgroundColor: colors.surface3, borderRadius: 18, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: 'transparent' },
  cardExpired: { opacity: 0.55 },
  topRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 12 },
  iconWrap: { width: 36, height: 36, borderRadius: 11, backgroundColor: 'rgba(99,102,241,0.12)', alignItems: 'center', justifyContent: 'center' },
  icon: { fontSize: 14, color: colors.indigo },
  label: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 2 },
  created: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  statusBadge: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, alignSelf: 'flex-start' },
  statusActive: { backgroundColor: 'rgba(52,211,153,0.13)' },
  statusExpired: { backgroundColor: 'rgba(148,163,184,0.12)' },
  statusText: { fontFamily: fonts.mono, fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  statusTextActive: { color: '#059669' },
  statusTextExpired: { color: colors.ink3 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaIcon: { fontSize: 11 },
  metaText: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  metaDot: { width: 3, height: 3, borderRadius: 2, backgroundColor: colors.ink3 },
  usageBarWrap: { height: 3, backgroundColor: 'rgba(0,0,0,0.07)', borderRadius: 2, marginBottom: 12, overflow: 'hidden' },
  usageBar: { height: 3, backgroundColor: colors.indigo, borderRadius: 2 },
  revokeBtn: { borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: 12, paddingVertical: 9, alignItems: 'center' },
  revokeBtnText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#FB7185' },
});

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyShares() {
  return (
    <View style={em.wrap}>
      <View style={em.icon}><Text style={em.iconText}>↗</Text></View>
      <Text style={em.title}>{tUi('NO_SHARE_LINKS_YET')}</Text>
      <Text style={em.sub}>
        When you share a document with a bank, recruiter, or anyone else, the link appears here — with a one-tap revoke.
      </Text>
      <Pressable onPress={() => router.push('/(vault)/vault/create-share')}>
        <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={em.btn}>
          <Text style={em.btnText}>Share a document</Text>
        </LinearGradient>
      </Pressable>
    </View>
  );
}
const em = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28, paddingBottom: 80 },
  icon: { width: 80, height: 80, borderRadius: 24, backgroundColor: 'rgba(99,102,241,0.10)', alignItems: 'center', justifyContent: 'center', marginBottom: 18 },
  iconText: { fontSize: 34, color: colors.indigo },
  title: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.ink, marginBottom: 8 },
  sub: { fontSize: 13, color: colors.ink2, lineHeight: 20, textAlign: 'center', maxWidth: 260, marginBottom: 22 },
  btn: { borderRadius: 16 },
  btnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C', paddingHorizontal: 24, paddingVertical: 14 },
});

// ── Screen ────────────────────────────────────────────────────────────────────

export default function SharesScreen() {
  const { data, loading, error, refetch } = useShares();
  const [revoking, setRevoking] = useState<ShareLink | null>(null);
  const [revokeLoading, setRevokeLoading] = useState(false);

  const shares = data?.shares ?? [];
  const active  = shares.filter(s => s.status === 'ACTIVE' && !isExpired(s.expires_at));
  const expired = shares.filter(s => s.status !== 'ACTIVE' ||  isExpired(s.expires_at));

  async function handleRevoke() {
    if (!revoking) return;
    setRevokeLoading(true);
    try {
      await api.delete(`/vault/shares/${revoking.token_id}`);
      setRevoking(null);
      refetch();
    } catch {
      setRevoking(null);
    } finally {
      setRevokeLoading(false);
    }
  }

  return (
    <View style={s.screen}>
      {revoking && (
        <RevokeSheet
          share={revoking}
          onConfirm={handleRevoke}
          onCancel={() => setRevoking(null)}
          loading={revokeLoading}
        />
      )}

      {/* Header */}
      <LinearGradient colors={['#0B0F1E', '#131B33']} style={s.header}>
        <SafeAreaView edges={['top']}>
          <View style={s.headerRow}>
            <Pressable style={s.backBtn} onPress={() => router.back()}>
              <Text style={s.backIcon}>←</Text>
            </Pressable>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={s.headerTitle}>Share links</Text>
              <Text style={s.headerSub}>You control every door out of your vault</Text>
            </View>
            <Pressable
              style={s.newBtn}
              onPress={() => router.push('/(vault)/vault/create-share')}
            >
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={s.newBtnGrad}>
                <Text style={s.newBtnText}>＋ New</Text>
              </LinearGradient>
            </Pressable>
          </View>
        </SafeAreaView>
      </LinearGradient>

      {/* Body */}
      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={colors.indigo} />
          <Text style={s.centerText}>Loading shares…</Text>
        </View>
      ) : shares.length === 0 ? (
        <EmptyShares />
      ) : (
        <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>
          {/* Control summary */}
          <View style={s.summaryCard}>
            <View style={s.summaryItem}>
              <Text style={s.summaryValue}>{active.length}</Text>
              <Text style={s.summaryLabel}>Active links</Text>
            </View>
            <View style={s.summaryDivider} />
            <View style={s.summaryItem}>
              <Text style={s.summaryValue}>{shares.reduce((n, s) => n + s.usage_count, 0)}</Text>
              <Text style={s.summaryLabel}>Total views</Text>
            </View>
            <View style={s.summaryDivider} />
            <View style={s.summaryItem}>
              <Text style={s.summaryValue}>{expired.length}</Text>
              <Text style={s.summaryLabel}>Expired</Text>
            </View>
          </View>

          {active.length > 0 && (
            <>
              <Text style={s.sectionLabel}>ACTIVE  ({active.length})</Text>
              {active.map(share => (
                <ShareCard key={share.token_id} share={share} onRevoke={setRevoking} />
              ))}
            </>
          )}

          {expired.length > 0 && (
            <>
              <Text style={[s.sectionLabel, { marginTop: 14 }]}>EXPIRED  ({expired.length})</Text>
              {expired.map(share => (
                <ShareCard key={share.token_id} share={share} onRevoke={setRevoking} />
              ))}
            </>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: 16, paddingBottom: 14 },
  headerRow: { flexDirection: 'row', alignItems: 'center', paddingTop: 10 },
  backBtn: { width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  backIcon: { fontSize: 16, color: '#FFFFFF' },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: '#FFFFFF', letterSpacing: -0.2 },
  headerSub: { fontFamily: fonts.mono, fontSize: 10, color: '#9CA8C9', marginTop: 2 },
  newBtn: {},
  newBtnGrad: { borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8 },
  newBtnText: { fontFamily: fonts.displayBold, fontSize: 13, color: '#04261C' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 14 },
  centerText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.ink3 },
  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 100 },
  summaryCard: { flexDirection: 'row', backgroundColor: colors.surface3, borderRadius: 16, padding: 16, marginBottom: 20, alignItems: 'center' },
  summaryItem: { flex: 1, alignItems: 'center' },
  summaryValue: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink, letterSpacing: -0.5 },
  summaryLabel: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  summaryDivider: { width: 1, height: 36, backgroundColor: colors.surface },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2, marginBottom: 10 },
});
