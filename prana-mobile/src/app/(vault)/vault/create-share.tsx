/**
 * Create share screen — build a time-limited link for one or more documents.
 *
 * Emotional job: "You're in control. You choose what they see and for how long."
 *
 * The employee picks documents, sets an expiry, adds an optional label
 * (e.g. "For HDFC home loan"), and gets a link they can send themselves.
 * PRANA never sends on their behalf.
 *
 * API: POST /vault/shares
 *   body: { document_ids, label?, expires_hours, usage_limit? }
 *   → { token_id, share_url, expires_at }
 */
import React, { useState, useMemo } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  TextInput, ActivityIndicator, Modal,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { useDocuments, createShare, type VaultDocument } from '@/hooks/useVault';
import { SOURCE_META } from '@/prana-components/DocumentCard';

const DOC_TYPE_LABELS: Record<string, string> = {
  SALARY_SLIP: 'Salary Slip', FORM_16: 'Form 16', INVESTMENT_PROOF: 'Investment Proof',
  IT_RETURN: 'ITR', BANK_STATEMENT: 'Bank Statement', OFFER_LETTER: 'Offer Letter',
  JOINING_LETTER: 'Joining Letter', APPRAISAL_LETTER: 'Appraisal Letter',
  BONUS_LETTER: 'Bonus Letter', PROMOTION_LETTER: 'Promotion Letter',
  RELIEVING_LETTER: 'Relieving Letter', EXPERIENCE_LETTER: 'Experience Letter',
};

const EXPIRY_OPTIONS = [
  { hours: 24,  label: '24 hours', sub: 'Same-day use',          tag: '24H' },
  { hours: 168, label: '7 days',   sub: 'Standard',               tag: '7D' },
  { hours: 720, label: '30 days',  sub: 'Loan / visa applications',tag: '30D' },
  { hours: 2160,label: '90 days',  sub: 'Long-term access',       tag: '90D' },
];

// ── Doc picker row ────────────────────────────────────────────────────────────

function DocRow({
  doc, selected, onToggle,
}: { doc: VaultDocument; selected: boolean; onToggle: () => void }) {
  const src = SOURCE_META[doc.source_type as keyof typeof SOURCE_META] ?? SOURCE_META.EMPLOYER_PUSH;
  return (
    <Pressable style={[dr.row, selected && dr.rowSelected]} onPress={onToggle}>
      <View style={[dr.checkbox, selected && dr.checkboxOn]}>
        {selected && <Text style={dr.check}>✓</Text>}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[dr.title, selected && dr.titleSelected]} numberOfLines={1}>{doc.title}</Text>
        <View style={dr.meta}>
          <Text style={[dr.src, { color: src.color }]}>{src.icon} {doc.issuer}</Text>
          <Text style={dr.dot}>·</Text>
          <Text style={dr.type}>{DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}</Text>
        </View>
      </View>
    </Pressable>
  );
}
const dr = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  rowSelected: { },
  checkbox: { width: 22, height: 22, borderRadius: 7, borderWidth: 2, borderColor: colors.ink3, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  checkboxOn: { backgroundColor: colors.indigo, borderColor: colors.indigo },
  check: { fontSize: 12, color: '#FFFFFF', fontWeight: '700' },
  title: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 2 },
  titleSelected: { color: colors.indigo },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  src: { fontFamily: fonts.mono, fontSize: 10 },
  dot: { fontSize: 10, color: colors.ink3 },
  type: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
});

// ── Created link sheet ────────────────────────────────────────────────────────

function CreatedLinkSheet({
  shareUrl, expiresAt, count, onDone,
}: { shareUrl: string; expiresAt: string; count: number; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() { setCopied(true); setTimeout(() => setCopied(false), 2500); }

  return (
    <Modal transparent animationType="slide">
      <View style={cl.overlay}>
        <View style={cl.panel}>
          <View style={cl.successCircle}>
            <LinearGradient colors={['#34D399', '#22D3EE']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={cl.successGrad}>
              <Text style={cl.successTick}>↗</Text>
            </LinearGradient>
          </View>
          <Text style={cl.title}>Link created</Text>
          <Text style={cl.sub}>
            {count} document{count > 1 ? 's' : ''} · expires {new Date(expiresAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
          </Text>
          <Text style={cl.sub}>Revocable from Shares at any time.</Text>

          <View style={cl.linkBox}>
            <Text style={cl.linkText} numberOfLines={1} selectable>{shareUrl}</Text>
            <Pressable style={[cl.copyBtn, copied && cl.copyBtnDone]} onPress={handleCopy}>
              <Text style={cl.copyText}>{copied ? '✓ Copied' : 'Copy'}</Text>
            </Pressable>
          </View>

          <View style={cl.privacyNote}>
            <Text style={cl.privacyText}>🔒  Recipient sees document details only — no salary figures, no PAN. You can revoke at any time.</Text>
          </View>

          <Pressable onPress={onDone} style={cl.doneBtn}>
            <Text style={cl.doneBtnText}>Done</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}
const cl = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  panel: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 },
  successCircle: { alignSelf: 'center', marginBottom: 16 },
  successGrad: { width: 64, height: 64, borderRadius: 32, alignItems: 'center', justifyContent: 'center' },
  successTick: { fontSize: 26, color: '#04261C', fontWeight: '700' },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink, textAlign: 'center', marginBottom: 6 },
  sub: { fontSize: 13, color: colors.ink3, textAlign: 'center', lineHeight: 20, marginBottom: 2 },
  linkBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface3, borderRadius: 12, padding: 10, gap: 8, marginVertical: 16 },
  linkText: { flex: 1, fontFamily: fonts.mono, fontSize: 11, color: colors.ink2 },
  copyBtn: { backgroundColor: colors.indigo, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 },
  copyBtnDone: { backgroundColor: colors.emerald },
  copyText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: '#FFFFFF' },
  privacyNote: { backgroundColor: 'rgba(52,211,153,0.07)', borderRadius: 10, padding: 10, marginBottom: 20 },
  privacyText: { fontFamily: fonts.mono, fontSize: 10, color: '#047857', lineHeight: 16 },
  doneBtn: { backgroundColor: colors.surface3, borderRadius: 16, height: 52, alignItems: 'center', justifyContent: 'center' },
  doneBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink },
});

// ── Screen ────────────────────────────────────────────────────────────────────

export default function CreateShareScreen() {
  const params = useLocalSearchParams<{ preselect?: string }>();
  const { data, loading: docsLoading } = useDocuments();

  const allDocs: VaultDocument[] = data?.documents ?? [];

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(params.preselect ? [params.preselect] : [])
  );
  const [expiryHours, setExpiryHours] = useState(168);
  const [label, setLabel] = useState('');
  const [usageLimit, setUsageLimit] = useState<number | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState<{ share_url: string; expires_at: string } | null>(null);

  // Filter state
  const [search, setSearch] = useState('');
  const filteredDocs = useMemo(() =>
    allDocs.filter(d =>
      !search || d.title.toLowerCase().includes(search.toLowerCase()) || d.issuer.toLowerCase().includes(search.toLowerCase())
    ),
    [allDocs, search]
  );

  function toggleDoc(id: string) {
    setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  async function handleCreate() {
    if (selectedIds.size === 0 || creating) return;
    setError('');
    setCreating(true);
    try {
      const res = await createShare({
        document_ids: Array.from(selectedIds),
        label: label.trim() || undefined,
        expires_hours: expiryHours,
        usage_limit: usageLimit,
      });
      setCreated({ share_url: res.share_url, expires_at: res.expires_at });
    } catch {
      setError('Couldn\'t create share link. Check your connection and try again.');
    } finally {
      setCreating(false);
    }
  }

  const canCreate = selectedIds.size > 0 && !creating;

  return (
    <View style={s.screen}>
      {created && (
        <CreatedLinkSheet
          shareUrl={created.share_url}
          expiresAt={created.expires_at}
          count={selectedIds.size}
          onDone={() => { setCreated(null); router.replace('/(vault)/shares'); }}
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
              <Text style={s.headerTitle}>Create share link</Text>
              <Text style={s.headerSub}>You control what they see and for how long</Text>
            </View>
          </View>
        </SafeAreaView>
      </LinearGradient>

      <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

        {/* ── Document selection ── */}
        <Text style={s.sectionLabel}>SELECT DOCUMENTS  ({selectedIds.size} selected)</Text>

        {/* Search */}
        <View style={s.searchWrap}>
          <Text style={s.searchIcon}>🔍</Text>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search by title or company…"
            placeholderTextColor={colors.ink3}
            style={s.searchInput}
          />
        </View>

        <View style={s.docList}>
          {docsLoading ? (
            <View style={s.docsLoading}>
              <ActivityIndicator size="small" color={colors.indigo} />
            </View>
          ) : allDocs.length === 0 ? (
            <View style={s.emptyDocs}>
              <Text style={s.emptyDocsEmoji}>📂</Text>
              <Text style={s.emptyDocsText}>No documents in your vault yet</Text>
              <Text style={s.emptyDocsSub}>Documents pushed by your employer will appear here</Text>
            </View>
          ) : (
            filteredDocs.map(doc => (
              <DocRow
                key={doc.id}
                doc={doc}
                selected={selectedIds.has(doc.id)}
                onToggle={() => toggleDoc(doc.id)}
              />
            ))
          )}
        </View>

        {/* ── Expiry ── */}
        <Text style={[s.sectionLabel, { marginTop: 20 }]}>LINK EXPIRES IN</Text>
        <View style={s.expiryGrid}>
          {EXPIRY_OPTIONS.map(opt => (
            <Pressable
              key={opt.hours}
              style={[s.expiryChip, expiryHours === opt.hours && s.expiryChipActive]}
              onPress={() => setExpiryHours(opt.hours)}
            >
              <Text style={[s.expiryTag, expiryHours === opt.hours && s.expiryTagActive]}>{opt.tag}</Text>
              <Text style={[s.expiryLabel, expiryHours === opt.hours && s.expiryLabelActive]}>{opt.label}</Text>
              <Text style={[s.expirySub, expiryHours === opt.hours && s.expirySubActive]}>{opt.sub}</Text>
            </Pressable>
          ))}
        </View>

        {/* ── Label ── */}
        <Text style={[s.sectionLabel, { marginTop: 20 }]}>LABEL  <Text style={s.optional}>(optional)</Text></Text>
        <TextInput
          value={label}
          onChangeText={setLabel}
          placeholder="e.g. HDFC home loan, Visa application…"
          placeholderTextColor={colors.ink3}
          style={s.labelInput}
          maxLength={60}
        />

        {/* ── Privacy note ── */}
        <View style={s.privacyNote}>
          <Text style={s.privacyNoteText}>🔒  Recipients see document details only — no salary figures, no PAN, no account numbers. The link auto-expires and is revocable any time.</Text>
        </View>

        {error ? <Text style={s.error}>{error}</Text> : null}

        {/* ── CTA ── */}
        <Pressable onPress={handleCreate} disabled={!canCreate}>
          <LinearGradient
            colors={gradJourney.colors}
            locations={gradJourney.locations}
            start={gradJourney.start}
            end={gradJourney.end}
            style={[s.createBtn, !canCreate && { opacity: 0.4 }]}
          >
            {creating
              ? <ActivityIndicator size="small" color="#04261C" />
              : <Text style={s.createBtnText}>
                  {selectedIds.size === 0
                    ? 'Select documents to share'
                    : `Create link for ${selectedIds.size} document${selectedIds.size > 1 ? 's' : ''} →`}
                </Text>
            }
          </LinearGradient>
        </Pressable>
      </ScrollView>
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
  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 40 },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2, marginBottom: 10 },
  optional: { fontWeight: '400', color: colors.ink3 },
  searchWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface3, borderRadius: 12, paddingHorizontal: 12, marginBottom: 2 },
  searchIcon: { fontSize: 13, marginRight: 6 },
  searchInput: { flex: 1, height: 42, fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink },
  docList: { backgroundColor: colors.surface3, borderRadius: 14, paddingHorizontal: 14, marginBottom: 4 },
  docsLoading: { paddingVertical: 24, alignItems: 'center' },
  emptyDocs: { paddingVertical: 32, alignItems: 'center' },
  emptyDocsEmoji: { fontSize: 36, marginBottom: 12 },
  emptyDocsText: { fontFamily: fonts.bodySemiBold, fontSize: 15, color: colors.ink, marginBottom: 6 },
  emptyDocsSub: { fontFamily: fonts.bodyRegular, fontSize: 12, color: colors.ink3, textAlign: 'center' },
  expiryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  expiryChip: { width: '47%', borderWidth: 1.5, borderColor: colors.surface3, borderRadius: 14, padding: 12, backgroundColor: colors.surface3 },
  expiryChipActive: { borderColor: colors.indigo, backgroundColor: 'rgba(99,102,241,0.07)' },
  expiryTag: { fontFamily: fonts.mono, fontSize: 13, fontWeight: '700', color: colors.ink3, marginBottom: 2 },
  expiryTagActive: { color: colors.indigo },
  expiryLabel: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.ink, marginBottom: 2 },
  expiryLabelActive: { color: colors.indigo },
  expirySub: { fontSize: 10, color: colors.ink3 },
  expirySubActive: { color: colors.indigo },
  labelInput: { borderWidth: 1.5, borderColor: colors.surface3, borderRadius: 12, padding: 12, fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink, backgroundColor: colors.surface3 },
  privacyNote: { backgroundColor: 'rgba(52,211,153,0.07)', borderWidth: 1, borderColor: 'rgba(52,211,153,0.16)', borderRadius: 12, padding: 12, marginVertical: 16 },
  privacyNoteText: { fontFamily: fonts.mono, fontSize: 10, color: '#047857', lineHeight: 17 },
  error: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.rose, textAlign: 'center', marginBottom: 12 },
  createBtn: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  createBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },
});
