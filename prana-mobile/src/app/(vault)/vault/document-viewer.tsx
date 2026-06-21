/**
 * Document viewer — full-screen view of a single vault document.
 *
 * Privacy contract: insights shown here are NON-SENSITIVE fields only.
 * The AI pipeline strips gross_salary, basic_salary, net_salary, hra,
 * pf_employee, pf_employer, total_deductions, ctc_before, ctc_after
 * BEFORE storing. We never show those here.
 *
 * What IS shown: roles, dates, designations, departments, periods,
 * policy numbers, percentages, qualitative assessments.
 *
 * API:
 *   GET  /vault/documents/{id}         → document metadata + insights
 *   GET  /vault/documents/{id}/download → { presigned_url }
 *   POST /vault/shares                  → { share_url, token_id, expires_at }
 */
import React, { useState } from 'react';
import {
  View, Text, ScrollView, Pressable, StyleSheet,
  Modal, ActivityIndicator, TextInput, Linking, TouchableWithoutFeedback,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney, docIconGradients } from '@/prana-theme/tokens';
import { useDocument, getDownloadUrl, createShare } from '@/hooks/useVault';
import { SOURCE_META } from '@/prana-components/DocumentCard';

// ── Share bottom sheet ────────────────────────────────────────────────────────
const EXPIRY_OPTIONS = [
  { hours: 24,  label: '24 hours', sub: 'Quick access — same-day use' },
  { hours: 168, label: '7 days',   sub: 'Standard — most requests' },
  { hours: 720, label: '30 days',  sub: 'Extended — loan applications' },
];

function ShareSheet({
  docId, docTitle, onClose,
}: { docId: string; docTitle: string; onClose: () => void }) {
  const [expiryHours, setExpiryHours] = useState(168);
  const [label, setLabel] = useState('');
  const [loading, setLoading]   = useState(false);
  const [shareUrl, setShareUrl] = useState('');
  const [copied,   setCopied]   = useState(false);
  const [error,    setError]    = useState('');

  async function handleCreate() {
    if (loading || shareUrl) return;
    setError('');
    setLoading(true);
    try {
      const res = await createShare({
        document_ids: [docId],
        label: label.trim() || undefined,
        expires_hours: expiryHours,
      });
      setShareUrl(res.share_url);
    } catch {
      setError('Couldn\'t create share link. Try again.');
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
    // Clipboard.setStringAsync(shareUrl); — add expo-clipboard if needed
  }

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={ss.overlay}>
          <View style={ss.panel}>
          <View style={ss.handle} />

          <Text style={ss.title}>Share document</Text>
          <View style={ss.docPill}>
            <Text style={ss.docPillText} numberOfLines={1}>{docTitle}</Text>
          </View>

          {!shareUrl ? (
            <>
              {/* Expiry picker */}
              <Text style={ss.sectionLabel}>LINK EXPIRES IN</Text>
              <View style={ss.expiryRow}>
                {EXPIRY_OPTIONS.map(opt => (
                  <Pressable
                    key={opt.hours}
                    onPress={() => setExpiryHours(opt.hours)}
                    style={[ss.expiryChip, expiryHours === opt.hours && ss.expiryChipActive]}
                  >
                    <Text style={[ss.expiryLabel, expiryHours === opt.hours && ss.expiryLabelActive]}>{opt.label}</Text>
                    <Text style={[ss.expirySub, expiryHours === opt.hours && ss.expirySubActive]}>{opt.sub}</Text>
                  </Pressable>
                ))}
              </View>

              {/* Optional label */}
              <Text style={ss.sectionLabel}>LABEL (optional)</Text>
              <TextInput
                value={label}
                onChangeText={setLabel}
                placeholder="e.g. For loan application"
                placeholderTextColor="#8B93A7"
                style={ss.labelInput}
                maxLength={60}
              />

              {/* Privacy note */}
              <View style={ss.privacyNote}>
                <Text style={ss.privacyText}>🔒  Recipient sees document content only. No salary figures — only role, dates, and issuer details.</Text>
              </View>

              {error ? <Text style={ss.error}>{error}</Text> : null}

              <Pressable onPress={handleCreate} disabled={loading}>
                <LinearGradient
                  colors={gradJourney.colors}
                  locations={gradJourney.locations}
                  start={gradJourney.start}
                  end={gradJourney.end}
                  style={[ss.createBtn, loading && { opacity: 0.6 }]}
                >
                  {loading
                    ? <ActivityIndicator size="small" color="#04261C" />
                    : <Text style={ss.createBtnText}>Create share link →</Text>
                  }
                </LinearGradient>
              </Pressable>
            </>
          ) : (
            <>
              {/* Share link created */}
              <View style={ss.successIcon}>
                <Text style={ss.successEmoji}>✓</Text>
              </View>
              <Text style={ss.successTitle}>Link created</Text>
              <Text style={ss.successSub}>
                Expires in {EXPIRY_OPTIONS.find(o => o.hours === expiryHours)?.label}.{'\n'}
                Revokable from Shares at any time.
              </Text>

              <View style={ss.linkBox}>
                <Text style={ss.linkText} numberOfLines={1} selectable>{shareUrl}</Text>
                <Pressable style={[ss.copyBtn, copied && ss.copyBtnDone]} onPress={handleCopy}>
                  <Text style={ss.copyText}>{copied ? '✓ Copied' : 'Copy'}</Text>
                </Pressable>
              </View>
            </>
          )}

          <Pressable style={ss.cancelBtn} onPress={onClose}>
            <Text style={ss.cancelText}>{shareUrl ? 'Done' : 'Cancel'}</Text>
          </Pressable>
          </View>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}

const ss = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  panel: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 36 },
  handle: { width: 36, height: 4, backgroundColor: colors.surface3, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  title: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, marginBottom: 8 },
  docPill: { backgroundColor: colors.surface3, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, alignSelf: 'flex-start', marginBottom: 20 },
  docPillText: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink2 },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2, marginBottom: 10 },
  expiryRow: { gap: 8, marginBottom: 18 },
  expiryChip: { borderWidth: 1, borderColor: colors.surface3, borderRadius: 12, padding: 12, backgroundColor: colors.surface3 },
  expiryChipActive: { borderColor: colors.indigo, backgroundColor: 'rgba(99,102,241,0.06)' },
  expiryLabel: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 2 },
  expiryLabelActive: { color: colors.indigo },
  expirySub: { fontSize: 11, color: colors.ink3 },
  expirySubActive: { color: colors.indigo },
  labelInput: { borderWidth: 1.5, borderColor: colors.surface3, borderRadius: 12, padding: 12, fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.ink, marginBottom: 14 },
  privacyNote: { backgroundColor: 'rgba(52,211,153,0.07)', borderWidth: 1, borderColor: 'rgba(52,211,153,0.18)', borderRadius: 10, padding: 10, marginBottom: 14 },
  privacyText: { fontFamily: fonts.mono, fontSize: 10, color: '#047857', lineHeight: 16 },
  error: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.rose, textAlign: 'center', marginBottom: 10 },
  createBtn: { borderRadius: 16, height: 52, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  createBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },
  successIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: 'rgba(52,211,153,0.15)', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: 12 },
  successEmoji: { fontSize: 24, color: colors.emerald, fontWeight: '700' },
  successTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, textAlign: 'center', marginBottom: 6 },
  successSub: { fontSize: 13, color: colors.ink3, textAlign: 'center', lineHeight: 20, marginBottom: 20 },
  linkBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface3, borderRadius: 12, padding: 10, gap: 8, marginBottom: 16 },
  linkText: { flex: 1, fontFamily: fonts.mono, fontSize: 11, color: colors.ink2 },
  copyBtn: { backgroundColor: colors.indigo, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 },
  copyBtnDone: { backgroundColor: colors.emerald },
  copyText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#FFFFFF' },
  cancelBtn: { alignItems: 'center', paddingVertical: 14 },
  cancelText: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink3 },
});

// ── Provenance chain ──────────────────────────────────────────────────────────
function ProvenanceChain({ sourceType, issuer, receivedAt, fileHash }: {
  sourceType: string; issuer: string; receivedAt: string; fileHash?: string;
}) {
  const src = SOURCE_META[sourceType as keyof typeof SOURCE_META] ?? SOURCE_META.EMPLOYER_PUSH;
  const dateStr = new Date(receivedAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });

  const steps = [
    { icon: src.icon, label: `${src.label === 'Employer' ? `Issued by ${issuer}` : src.label === 'Email' ? `Captured from email (${issuer})` : 'Uploaded by you'}`, sub: dateStr, color: src.color },
    { icon: '🔒', label: 'Encrypted & stored in PRANA vault', sub: fileHash ? `SHA-256: ${fileHash.slice(0, 16)}…` : 'Hash sealed at upload', color: colors.indigo },
    { icon: '✦',  label: 'Tamper-proof vault record', sub: 'Verifiable on request', color: colors.cyan },
  ];

  return (
    <View>
      <Text style={pv.heading}>PROVENANCE CHAIN</Text>
      {steps.map((step, i) => (
        <View key={i} style={pv.row}>
          <View style={pv.left}>
            <View style={[pv.dot, { borderColor: step.color + '55', backgroundColor: step.color + '18' }]}>
              <Text style={pv.dotIcon}>{step.icon}</Text>
            </View>
            {i < steps.length - 1 && <View style={[pv.line, { backgroundColor: step.color + '30' }]} />}
          </View>
          <View style={pv.content}>
            <Text style={pv.label}>{step.label}</Text>
            <Text style={pv.sub}>{step.sub}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}
const pv = StyleSheet.create({
  heading: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: '#5C6685', letterSpacing: 1.2, marginBottom: 14 },
  row: { flexDirection: 'row', gap: 12, minHeight: 52 },
  left: { alignItems: 'center', width: 34 },
  dot: { width: 34, height: 34, borderRadius: 11, borderWidth: 1, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  dotIcon: { fontSize: 14 },
  line: { flex: 1, width: 2, borderRadius: 1, marginVertical: 3 },
  content: { flex: 1, paddingBottom: 16 },
  label: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#FFFFFF', marginBottom: 2 },
  sub: { fontFamily: fonts.mono, fontSize: 10, color: '#8B93A7' },
});

// ── Main screen ───────────────────────────────────────────────────────────────
export default function DocumentViewerScreen() {
  const { profile } = useAuth();
  const params = useLocalSearchParams<{ id?: string; action?: string }>();
  const docId = params.id ?? '';

  const { data, loading, error } = useDocument(docId);

  const apiDoc = data?.document;

  const insights: Record<string, string> =
    apiDoc?.insights
      ? Object.fromEntries(Object.entries(apiDoc.insights).map(([k, v]) => [k, v.value]))
      : { Document: 'Content available after processing' };

  const iconGrad = docIconGradients[(apiDoc?.icon_type ?? '') as keyof typeof docIconGradients] ?? docIconGradients.salary;
  const src = SOURCE_META[(apiDoc?.source_type ?? '') as keyof typeof SOURCE_META] ?? SOURCE_META.EMPLOYER_PUSH;

  const watermarkLine = `PRANA VERIFIED  ·  ${profile?.vault_url ?? 'prana.in/vault'}  ·  `;
  const watermark = Array(50).fill(watermarkLine).join('');

  const [shareVisible, setShareVisible] = useState(params.action === 'share');
  const [downloading, setDownloading]   = useState(false);

  async function handleDownload() {
    if (downloading) return;
    setDownloading(true);
    try {
      const url = await getDownloadUrl(apiDoc?.id ?? '');
      await Linking.openURL(url);
    } catch {
      // fail silently — user can retry
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return (
      <View style={s.loadScreen}>
        <ActivityIndicator size="large" color={colors.indigo} />
        <Text style={s.loadText}>Loading document…</Text>
      </View>
    );
  }

  if (error && !apiDoc) {
    return (
      <View style={s.loadScreen}>
        <Text style={s.errorEmoji}>⚠</Text>
        <Text style={s.errorTitle}>Couldn't load document</Text>
        <Pressable onPress={() => router.back()} style={s.backPill}>
          <Text style={s.backPillText}>← Go back</Text>
        </Pressable>
      </View>
    );
  }

  if (!apiDoc) {
    return (
      <View style={s.loadScreen}>
        <Text style={s.errorEmoji}>📄</Text>
        <Text style={s.errorTitle}>Document not found</Text>
        <Pressable onPress={() => router.back()} style={s.backPill}>
          <Text style={s.backPillText}>← Go back</Text>
        </Pressable>
      </View>
    );
  }

  const doc = apiDoc;

  return (
    <View style={s.screen}>
      {shareVisible && (
        <ShareSheet docId={doc.id} docTitle={doc.title} onClose={() => setShareVisible(false)} />
      )}

      {/* Top bar */}
      <LinearGradient colors={['#0B0F1E', '#131B33']} style={s.topGrad}>
        <SafeAreaView edges={['top']}>
          <View style={s.topbar}>
            <Pressable style={s.backBtn} onPress={() => router.back()}>
              <Text style={s.backIcon}>←</Text>
            </Pressable>
            <View style={{ flex: 1, marginHorizontal: 12 }}>
              <Text style={s.topTitle} numberOfLines={1}>{doc.title}</Text>
              <Text style={s.topSub}>{doc.issuer}</Text>
            </View>
            <View style={s.topActions}>
              <Pressable
                style={[s.topBtn, downloading && { opacity: 0.6 }]}
                onPress={handleDownload}
                disabled={downloading}
              >
                {downloading
                  ? <ActivityIndicator size="small" color="#FFFFFF" />
                  : <Text style={s.topBtnIcon}>⬇</Text>
                }
              </Pressable>
              <Pressable style={s.shareTopBtn} onPress={() => setShareVisible(true)}>
                <Text style={s.shareTopIcon}>↗</Text>
                <Text style={s.shareTopLabel}>Share</Text>
              </Pressable>
            </View>
          </View>
        </SafeAreaView>
      </LinearGradient>

      <ScrollView style={s.scroll} contentContainerStyle={s.scrollContent} showsVerticalScrollIndicator={false}>

        {/* White document card */}
        <View style={s.docCard}>
          {/* Diagonal watermark */}
          <Text style={s.watermark} numberOfLines={80}>{watermark}</Text>

          {/* Doc header */}
          <View style={s.docHeader}>
            <LinearGradient colors={iconGrad.colors} start={iconGrad.start} end={iconGrad.end} style={s.docIcon}>
              <Text style={{ fontSize: 22 }}>{doc.icon_emoji}</Text>
            </LinearGradient>
            <View style={{ flex: 1 }}>
              <Text style={s.docTitle}>{doc.title}</Text>
              <Text style={s.docIssuer}>{doc.issuer}</Text>
            </View>
          </View>

          <View style={s.divider} />

          {/* Insight rows */}
          {Object.entries(insights).map(([k, v], i, arr) => (
            <View key={k} style={[s.row, i === arr.length - 1 && { borderBottomWidth: 0 }]}>
              <Text style={s.rowKey}>{k}</Text>
              <Text style={s.rowVal}>{v}</Text>
            </View>
          ))}

          {/* Source badge */}
          <View style={[s.sourceBadge, { backgroundColor: src.bg, borderColor: src.border }]}>
            <Text style={s.sourceBadgeIcon}>{src.icon}</Text>
            <Text style={[s.sourceBadgeText, { color: src.color }]}>
              {doc.source_type === 'EMPLOYER_PUSH'        ? `Employer pushed by ${doc.issuer}` :
               doc.source_type === 'EMAIL_FETCH'          ? `Auto-captured from email (${doc.issuer})` :
               doc.source_type === 'EMPLOYEE_SELF_UPLOAD' ? 'Uploaded by you' :
               'Third-party verified'}
            </Text>
          </View>

          {/* Privacy note — inside the doc card */}
          <View style={s.privacyNote}>
            <Text style={s.privacyText}>🔒  Salary figures are never stored or displayed. Only role, dates, and career details are shown.</Text>
          </View>
        </View>

        {/* Provenance chain */}
        <View style={s.provCard}>
          <ProvenanceChain
            sourceType={doc.source_type}
            issuer={doc.issuer}
            receivedAt={doc.received_at}
            fileHash={apiDoc?.file_hash}
          />
        </View>

        {/* Share CTA */}
        <Pressable onPress={() => setShareVisible(true)}>
          <LinearGradient
            colors={gradJourney.colors}
            locations={gradJourney.locations}
            start={gradJourney.start}
            end={gradJourney.end}
            style={s.shareBtn}
          >
            <Text style={s.shareBtnText}>↗  Share this document</Text>
          </LinearGradient>
        </Pressable>
      </ScrollView>

      {/* Footer — vault identity */}
      <SafeAreaView edges={['bottom']} style={s.footer}>
        <Text style={s.footerText}>
          🔐  {profile?.vault_url ?? 'prana.in/vault'}  ·  PRANA Verified
        </Text>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#0B0F1E' },

  loadScreen: { flex: 1, backgroundColor: '#0B0F1E', alignItems: 'center', justifyContent: 'center', gap: 16 },
  loadText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: '#8B93A7' },
  errorEmoji: { fontSize: 40 },
  errorTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: '#FFFFFF' },
  backPill: { marginTop: 8, paddingHorizontal: 20, paddingVertical: 10, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 20 },
  backPillText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#FFFFFF' },

  // Top bar
  topGrad: { paddingHorizontal: 16, paddingBottom: 14 },
  topbar: { flexDirection: 'row', alignItems: 'center', paddingTop: 8 },
  backBtn: { width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  backIcon: { fontSize: 16, color: '#FFFFFF' },
  topTitle: { fontFamily: fonts.displayBold, fontSize: 14, color: '#FFFFFF', letterSpacing: -0.1 },
  topSub: { fontFamily: fonts.mono, fontSize: 10, color: '#8B93A7', marginTop: 1 },
  topActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topBtn: { width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  topBtnIcon: { fontSize: 15, color: '#FFFFFF' },
  shareTopBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7 },
  shareTopIcon: { fontSize: 13, color: '#FFFFFF' },
  shareTopLabel: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#FFFFFF' },

  // Scroll
  scroll: { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 32, gap: 14 },

  // White doc card
  docCard: { backgroundColor: '#FFFFFF', borderRadius: 20, padding: 20, overflow: 'hidden', position: 'relative' },
  watermark: {
    position: 'absolute', top: -20, left: -20, right: -20, bottom: -20,
    fontSize: 10, color: '#000000', opacity: 0.03,
    transform: [{ rotate: '-28deg' }], lineHeight: 24, zIndex: 0,
  },
  docHeader: { flexDirection: 'row', gap: 12, alignItems: 'center', marginBottom: 14, zIndex: 1 },
  docIcon: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  docTitle: { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink, letterSpacing: -0.2 },
  docIssuer: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3, marginTop: 2 },
  divider: { height: 1, backgroundColor: 'rgba(0,0,0,0.07)', marginBottom: 10, zIndex: 1 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.05)', zIndex: 1 },
  rowKey: { fontSize: 12, color: colors.ink2, flex: 1 },
  rowVal: { fontFamily: fonts.mono, fontSize: 12, color: colors.ink, fontWeight: '600', textAlign: 'right', flex: 1 },

  sourceBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 14, borderRadius: 10, borderWidth: 1, padding: 10, zIndex: 1 },
  sourceBadgeIcon: { fontSize: 13 },
  sourceBadgeText: { fontFamily: fonts.bodySemiBold, fontSize: 12 },

  privacyNote: { marginTop: 10, backgroundColor: 'rgba(99,102,241,0.06)', borderRadius: 10, padding: 10, zIndex: 1 },
  privacyText: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink2, lineHeight: 16 },

  // Provenance card
  provCard: { backgroundColor: '#131B33', borderRadius: 18, padding: 18, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },

  // Share CTA
  shareBtn: { borderRadius: 16 },
  shareBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C', textAlign: 'center', padding: 16 },

  // Footer
  footer: { backgroundColor: '#0B0F1E', borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)' },
  footerText: { textAlign: 'center', fontFamily: fonts.mono, fontSize: 10, color: '#5C6685', paddingVertical: 10 },
});
