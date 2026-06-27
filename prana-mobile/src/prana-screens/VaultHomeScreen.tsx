/**
 * VaultHomeScreen — the heart of the PRANA mobile app.
 *
 * The vault is not a file manager. It's the employee's career record,
 * permanent and portable. Every design decision should reinforce:
 * "These documents are yours. They travel with you. Forever."
 *
 * Features:
 *  - Real API via useDocuments / useEmployers / useShares hooks
 *  - Company filter (All · per-employer · Self-uploaded · From email)
 *  - Doc-type filter with per-company live counts
 *  - Source badge on every card (🛡 Employer · 📧 Email · ⬆ Self · ✦ 3rd party)
 *  - Long-press → multi-select mode → ZIP download
 *  - Per-card actions: View · Download · Share
 *  - Notification bell with inline popup
 *  - Upload button → self-upload flow
 */
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  View, Text, ScrollView, Pressable, StyleSheet, Modal,
  ActivityIndicator, Linking,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { colors, fonts, radius, gradJourney, gradTopBg } from '../prana-theme/tokens';
import { StatCard } from '../prana-components/StatCard';
import { DocumentCard } from '../prana-components/DocumentCard';
import { VaultNav } from '../prana-components/VaultNav';
import { ZipModal } from '../components/DownloadFeedback';
import { useAuth } from '../context/AuthContext';
import {
  useDocuments, useEmployers, useShares,
  getDownloadUrl, createShare, requestZipDownload,
  type VaultDocument,
} from '../hooks/useVault';
import { mockDocuments } from '../mocks/documents';
import { mockCareer } from '../mocks/career';

// ── Constants ─────────────────────────────────────────────────────────────────

const DOC_TYPE_LABELS: Record<string, string> = {
  SALARY_SLIP:       'Salary Slips',
  FORM_16:           'Form 16',
  INVESTMENT_PROOF:  'Investment Proofs',
  IT_RETURN:         'IT Returns',
  BANK_STATEMENT:    'Bank Statements',
  OFFER_LETTER:      'Offer Letters',
  JOINING_LETTER:    'Joining Letters',
  APPRAISAL_LETTER:  'Appraisal Letters',
  BONUS_LETTER:      'Bonus Letters',
  PROMOTION_LETTER:  'Promotion Letters',
  RELIEVING_LETTER:  'Relieving Letters',
  EXPERIENCE_LETTER: 'Experience Letters',
};

const NOTIFICATION = {
  title: 'New document added',
  subtitle: 'Salary Slip — May 2026 pushed by NPCI',
  documentId: 'n_sal_01',
};

// ── Source helpers ────────────────────────────────────────────────────────────

function sourceToProvenance(doc: VaultDocument): 'EMPLOYER_PUSH' | 'EMPLOYEE_SELF_UPLOAD' | 'EMAIL_FETCH' | 'THIRD_PARTY_VERIFIED' {
  return doc.source_type as 'EMPLOYER_PUSH' | 'EMPLOYEE_SELF_UPLOAD' | 'EMAIL_FETCH' | 'THIRD_PARTY_VERIFIED';
}

// ── Company picker ────────────────────────────────────────────────────────────

interface CompanyPickerProps {
  visible: boolean;
  selected: string;
  onSelect: (id: string) => void;
  onClose: () => void;
  totalDocs: number;
  emailCount: number;
  selfCount: number;
  employers: { id: string; name: string; role?: string; from: string; to: string | null; docCount: number }[];
}

function CompanyPicker({ visible, selected, onSelect, onClose, totalDocs, emailCount, selfCount, employers }: CompanyPickerProps) {
  const options = [
    { id: 'ALL',   name: 'All sources',     sub: `${totalDocs} documents total`,              period: '', count: totalDocs,   icon: '🗂' },
    ...employers.map(e => ({
      id: e.id, name: e.name, sub: e.role ?? '',
      period: `${new Date(e.from).getFullYear()} – ${e.to ? new Date(e.to).getFullYear() : 'Present'}`,
      count: e.docCount, icon: '🏢',
    })),
    { id: 'EMAIL', name: 'From email',       sub: 'Auto-captured from your inbox',            period: '', count: emailCount,  icon: '📧' },
    { id: 'SELF',  name: 'Self-uploaded',    sub: 'Investment proofs, ITR, bank statements',  period: '', count: selfCount,   icon: '⬆' },
  ];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={ps.overlay} onPress={onClose}>
        <Pressable style={ps.sheet} onPress={e => e.stopPropagation()}>
          <View style={ps.handle} />
          <Text style={ps.title}>Filter by source</Text>
          <ScrollView showsVerticalScrollIndicator={false}>
            {options.map((o, i) => (
              <Pressable
                key={o.id}
                style={[ps.row, selected === o.id && ps.rowActive, i < options.length - 1 && ps.rowBorder]}
                onPress={() => { onSelect(o.id); onClose(); }}
              >
                <View style={ps.rowIconWrap}>
                  <Text style={ps.rowIconEmoji}>{o.icon}</Text>
                </View>
                <View style={ps.rowText}>
                  <Text style={[ps.rowName, selected === o.id && ps.rowNameActive]}>{o.name}</Text>
                  <Text style={ps.rowSub}>{o.sub}{o.period ? `  ·  ${o.period}` : ''}</Text>
                </View>
                <View style={[ps.countBadge, selected === o.id && ps.countBadgeActive]}>
                  <Text style={[ps.countText, selected === o.id && ps.countTextActive]}>{o.count}</Text>
                </View>
                {selected === o.id && <Text style={ps.check}>✓</Text>}
              </Pressable>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// ── Doc type picker ───────────────────────────────────────────────────────────

interface DocTypePickerProps {
  visible: boolean;
  selected: string;
  companyFilter: string;
  onSelect: (k: string) => void;
  onClose: () => void;
  documents: VaultDocument[];
}

function DocTypePicker({ visible, selected, companyFilter, onSelect, onClose, documents }: DocTypePickerProps) {
  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    documents.forEach(d => {
      if (matchesCompanyFilter(d, companyFilter)) {
        map[d.doc_type] = (map[d.doc_type] || 0) + 1;
      }
    });
    return map;
  }, [documents, companyFilter]);

  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const types = [
    { key: 'ALL', label: 'All types', count: total },
    ...Object.entries(DOC_TYPE_LABELS)
      .filter(([k]) => (counts[k] || 0) > 0)
      .map(([key, label]) => ({ key, label, count: counts[key] || 0 })),
  ];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={ps.overlay} onPress={onClose}>
        <Pressable style={ps.sheet} onPress={e => e.stopPropagation()}>
          <View style={ps.handle} />
          <Text style={ps.title}>Filter by document type</Text>
          <ScrollView showsVerticalScrollIndicator={false}>
            {types.map((t, i) => (
              <Pressable
                key={t.key}
                style={[ps.row, selected === t.key && ps.rowActive, i < types.length - 1 && ps.rowBorder]}
                onPress={() => { onSelect(t.key); onClose(); }}
              >
                <Text style={[ps.rowName, { flex: 1 }, selected === t.key && ps.rowNameActive]}>{t.label}</Text>
                <View style={[ps.countBadge, selected === t.key && ps.countBadgeActive]}>
                  <Text style={[ps.countText, selected === t.key && ps.countTextActive]}>{t.count}</Text>
                </View>
                {selected === t.key && <Text style={ps.check}>✓</Text>}
              </Pressable>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const ps = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 36, maxHeight: '80%' },
  handle: { width: 36, height: 4, backgroundColor: colors.surface3, borderRadius: 2, alignSelf: 'center', marginBottom: 18 },
  title: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.ink, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 13, gap: 10 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  rowActive: {},
  rowIconWrap: { width: 32, height: 32, borderRadius: 10, backgroundColor: colors.surface3, alignItems: 'center', justifyContent: 'center' },
  rowIconEmoji: { fontSize: 14 },
  rowText: { flex: 1 },
  rowName: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink },
  rowNameActive: { color: colors.indigo },
  rowSub: { fontSize: 11, color: colors.ink3, marginTop: 1 },
  countBadge: { paddingHorizontal: 9, paddingVertical: 3, borderRadius: 10, backgroundColor: colors.surface3 },
  countBadgeActive: { backgroundColor: 'rgba(99,102,241,0.12)' },
  countText: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3 },
  countTextActive: { color: colors.indigo },
  check: { fontSize: 14, color: colors.indigo, fontWeight: '700', marginLeft: 4 },
});

// ── Filter match helper ───────────────────────────────────────────────────────

function matchesCompanyFilter(doc: VaultDocument, filter: string): boolean {
  if (filter === 'ALL')   return true;
  if (filter === 'SELF')  return doc.source_type === 'EMPLOYEE_SELF_UPLOAD';
  if (filter === 'EMAIL') return doc.source_type === 'EMAIL_FETCH';
  return doc.employer_id === filter;
}

// ── Menu overlay ──────────────────────────────────────────────────────────────

function MenuPanel({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { profile, signOut } = useAuth();
  const items = [
    { icon: '🗂', label: 'My Vault',    sub: 'Documents & history',  route: '/(vault)/vault'     as const },
    { icon: '💼', label: 'Career',      sub: 'Employers & timeline', route: '/(vault)/career'    as const },
    { icon: '↗',  label: 'Shares',     sub: 'Active share links',    route: '/(vault)/shares'    as const },
    { icon: '⚙',  label: 'Settings',   sub: 'Account & devices',    route: '/(vault)/settings'  as const },
    { icon: '⚖',  label: 'My Rights',  sub: 'DPDP · Data export',   route: '/(vault)/data-rights' as const },
  ];
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={mp.overlay} onPress={onClose}>
        <Pressable style={mp.panel} onPress={e => e.stopPropagation()}>
          <View style={mp.profile}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={mp.avatar}>
              <Text style={mp.avatarText}>{(profile?.name ?? '?').charAt(0)}</Text>
            </LinearGradient>
            <View>
              <Text style={mp.name}>{profile?.name ?? '—'}</Text>
              <Text style={mp.url}>{profile?.vault_url ?? ''}</Text>
            </View>
          </View>
          <View style={mp.divider} />
          {items.map(item => (
            <Pressable key={item.label} style={mp.item} onPress={() => { onClose(); router.push(item.route); }}>
              <View style={mp.itemIcon}><Text style={{ fontSize: 15 }}>{item.icon}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={mp.itemLabel}>{item.label}</Text>
                <Text style={mp.itemSub}>{item.sub}</Text>
              </View>
            </Pressable>
          ))}
          <View style={mp.divider} />
          <Pressable style={mp.item} onPress={() => { onClose(); signOut(); router.replace('/(auth)/sign-in'); }}>
            <View style={[mp.itemIcon, { backgroundColor: 'rgba(251,113,133,0.12)' }]}><Text style={{ fontSize: 15 }}>🚪</Text></View>
            <Text style={mp.dangerLabel}>Sign out</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
const mp = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(10,14,28,0.6)', justifyContent: 'flex-start' },
  panel: { margin: 12, marginTop: 56, backgroundColor: 'rgba(18,26,52,0.97)', borderRadius: 22, padding: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)' },
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, paddingBottom: 14 },
  avatar: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontFamily: fonts.displayBold, fontSize: 16, color: '#04261C' },
  name: { fontFamily: fonts.displayBold, fontSize: 14, color: '#FFFFFF' },
  url: { fontFamily: fonts.mono, fontSize: 10, color: '#8B93A7', marginTop: 1 },
  divider: { height: 1, backgroundColor: 'rgba(255,255,255,0.08)', marginHorizontal: 8, marginVertical: 4 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10, borderRadius: 12 },
  itemIcon: { width: 32, height: 32, borderRadius: 9, backgroundColor: 'rgba(255,255,255,0.07)', alignItems: 'center', justifyContent: 'center' },
  itemLabel: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: '#E2E8F0' },
  itemSub: { fontSize: 11, color: '#8B93A7', marginTop: 1 },
  dangerLabel: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: '#FCA5A5' },
});

// ── Bell popup ────────────────────────────────────────────────────────────────

function BellPopup({ onClose, onTap }: { onClose: () => void; onTap: () => void }) {
  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={bp.overlay} onPress={onClose}>
        <Pressable style={bp.card} onPress={onTap}>
          <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={bp.icon}>
            <Text style={{ fontSize: 18 }}>📄</Text>
          </LinearGradient>
          <View style={{ flex: 1 }}>
            <Text style={bp.title}>{NOTIFICATION.title}</Text>
            <Text style={bp.sub}>{NOTIFICATION.subtitle}</Text>
          </View>
          <Pressable onPress={onClose}><Text style={bp.close}>✕</Text></Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
const bp = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'flex-start', paddingTop: 86, paddingHorizontal: 16 },
  card: { backgroundColor: '#1C2747', borderRadius: 16, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12, borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)' },
  icon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  title: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#FFFFFF', marginBottom: 2 },
  sub: { fontSize: 11, color: '#9CA8C9', lineHeight: 16 },
  close: { fontSize: 14, color: '#9CA8C9', padding: 4 },
});

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyVaultState() {
  return (
    <View style={ev.wrap}>
      <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={ev.icon}>
        <Text style={{ fontSize: 56 }}>🗂</Text>
      </LinearGradient>
      <Text style={ev.title}>Your vault is empty</Text>
      <Text style={ev.sub}>Documents pushed by your employer appear here automatically. You can also upload your own.</Text>
      <Pressable onPress={() => router.push('/(vault)/vault/self-upload')}>
        <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={ev.btn}>
          <Text style={ev.btnText}>Upload your first document</Text>
        </LinearGradient>
      </Pressable>
    </View>
  );
}
const ev = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28, paddingBottom: 110 },
  icon: { width: 110, height: 110, borderRadius: 32, alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  title: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.ink, marginBottom: 8 },
  sub: { fontSize: 13, color: colors.ink2, lineHeight: 20, textAlign: 'center', maxWidth: 260, marginBottom: 22 },
  btn: { borderRadius: 16 },
  btnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C', textAlign: 'center', paddingHorizontal: 24, paddingVertical: 14 },
});

// ── Section header with select-all ───────────────────────────────────────────

function SectionHeader({ label, count, selectionMode, allSelected, onSelectAll }: {
  label: string; count: number;
  selectionMode: boolean; allSelected: boolean; onSelectAll: () => void;
}) {
  return (
    <View style={sh.row}>
      <Text style={sh.label}>{label}  ({count})</Text>
      {selectionMode && (
        <Pressable onPress={onSelectAll} style={sh.selectAll}>
          <Text style={sh.selectAllText}>{allSelected ? 'Deselect all' : 'Select all'}</Text>
        </Pressable>
      )}
    </View>
  );
}
const sh = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  label: { flex: 1, fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2 },
  selectAll: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, backgroundColor: 'rgba(99,102,241,0.10)' },
  selectAllText: { fontFamily: fonts.bodySemiBold, fontSize: 11, color: colors.indigo },
});

// ── Source legend (shown when not filtered) ───────────────────────────────────

function SourceLegend() {
  const items: Array<[string, string, string]> = [
    ['🛡', '#059669', 'Employer'],
    ['📧', '#0891B2', 'Email'],
    ['⬆',  '#B45309', 'Self'],
  ];
  return (
    <View style={sl.row}>
      {items.map(([icon, color, label]) => (
        <View key={label} style={sl.item}>
          <Text style={sl.icon}>{icon}</Text>
          <Text style={[sl.label, { color }]}>{label}</Text>
        </View>
      ))}
    </View>
  );
}
const sl = StyleSheet.create({
  row: { flexDirection: 'row', gap: 12, marginBottom: 14, paddingLeft: 2 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  icon: { fontSize: 11 },
  label: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700' },
});

// ── VaultHomeScreen ───────────────────────────────────────────────────────────

export function VaultHomeScreen() {
  const { profile } = useAuth();

  // Data
  const { data: docsData, loading: docsLoading, refetch: refetchDocs } = useDocuments();
  const { data: employersData } = useEmployers();
  const { data: sharesData } = useShares();

  const apiDocs = docsData?.documents;
  const allDocuments: VaultDocument[] = apiDocs ?? (mockDocuments as unknown as VaultDocument[]);
  const employers = employersData?.employers ?? mockCareer.employers;
  const activeSharesCount = sharesData?.shares?.filter(s => s.status === 'ACTIVE').length ?? 2;

  // Filters
  const [companyFilter,  setCompanyFilter]  = useState('ALL');
  const [docTypeFilter,  setDocTypeFilter]  = useState('ALL');

  // Pickers
  const [companyPickerVisible,  setCompanyPickerVisible]  = useState(false);
  const [docTypePickerVisible,  setDocTypePickerVisible]  = useState(false);

  // Notifications
  const [bellBadge,   setBellBadge]   = useState(1);
  const [bellVisible, setBellVisible] = useState(false);

  // Menu
  const [menuVisible, setMenuVisible] = useState(false);

  // Multi-select
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds,   setSelectedIds]   = useState<Set<string>>(new Set());
  const [zipVisible,    setZipVisible]    = useState(false);
  const [zipLoading,    setZipLoading]    = useState(false);

  // Download feedback
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // ── Benchmarking nudge ────────────────────────────────────────────
  const [nudgeDismissed, setNudgeDismissed] = useState(true); // start hidden, reveal after check

  useEffect(() => {
    AsyncStorage.getItem('bench_nudge_dismissed').then(v => {
      if (!v) setNudgeDismissed(false);
    });
  }, []);

  const { data: benchConsentData } = useQuery({
    queryKey: ['benchmark-consent'],
    queryFn: () => api.get('/v1/benchmarking/consent').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const hasSalarySlip = useMemo(
    () => allDocuments.some(d => d.doc_type === 'SALARY_SLIP'),
    [allDocuments]
  );

  const showBenchNudge =
    !nudgeDismissed &&
    hasSalarySlip &&
    benchConsentData !== undefined &&
    benchConsentData?.peer_benchmark_consent === false;

  function dismissNudge() {
    setNudgeDismissed(true);
    AsyncStorage.setItem('bench_nudge_dismissed', '1');
  }

  // ── Derived counts for picker ──────────────────────────────────────
  const emailCount = useMemo(() => allDocuments.filter(d => d.source_type === 'EMAIL_FETCH').length, [allDocuments]);
  const selfCount  = useMemo(() => allDocuments.filter(d => d.source_type === 'EMPLOYEE_SELF_UPLOAD').length, [allDocuments]);

  const employersWithCounts = useMemo(() =>
    employers.map((e: any) => ({
      ...e,
      docCount: allDocuments.filter(d => d.employer_id === e.id).length,
    })),
    [employers, allDocuments]
  );

  // ── Filter ────────────────────────────────────────────────────────
  const filteredDocs = useMemo(() =>
    allDocuments.filter(doc =>
      matchesCompanyFilter(doc, companyFilter) &&
      (docTypeFilter === 'ALL' || doc.doc_type === docTypeFilter)
    ),
    [allDocuments, companyFilter, docTypeFilter]
  );

  // ── Labels ────────────────────────────────────────────────────────
  const companyLabel =
    companyFilter === 'ALL'   ? 'All sources' :
    companyFilter === 'SELF'  ? 'Self-uploaded' :
    companyFilter === 'EMAIL' ? 'From email' :
    employers.find((e: any) => e.id === companyFilter)?.name ?? 'All sources';

  const docTypeLabel = docTypeFilter === 'ALL'
    ? 'All types'
    : (DOC_TYPE_LABELS[docTypeFilter] ?? 'All types');

  const sectionLabel =
    companyFilter === 'ALL'
      ? 'ALL DOCUMENTS'
      : companyLabel.toUpperCase() + (docTypeFilter !== 'ALL' ? `  ·  ${docTypeLabel.toUpperCase()}` : '');

  // ── Selection helpers ─────────────────────────────────────────────
  function enterSelection(id: string) { setSelectionMode(true); setSelectedIds(new Set([id])); }
  function toggleSelect(id: string) {
    setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function cancelSelection() { setSelectionMode(false); setSelectedIds(new Set()); }
  function toggleSelectAll() {
    const allIds = filteredDocs.map(d => d.id);
    const allSelected = allIds.every(id => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(allIds));
  }
  const allFilteredSelected = filteredDocs.length > 0 && filteredDocs.every(d => selectedIds.has(d.id));

  // ── Download single ───────────────────────────────────────────────
  const handleDownload = useCallback(async (doc: VaultDocument) => {
    if (downloadingId) return;
    setDownloadingId(doc.id);
    try {
      const url = await getDownloadUrl(doc.id);
      await Linking.openURL(url);
    } catch {
      // Fallback: open a generic message — no toast dependency needed
    } finally {
      setDownloadingId(null);
    }
  }, [downloadingId]);

  // ── ZIP download ──────────────────────────────────────────────────
  async function handleZipDownload() {
    setZipLoading(true);
    try {
      const ids = Array.from(selectedIds);
      const res = await requestZipDownload(ids);
      if (res.download_url) await Linking.openURL(res.download_url);
    } catch {
      // ZipModal handles the UX
    } finally {
      setZipLoading(false);
      setZipVisible(false);
      cancelSelection();
    }
  }

  // ── Share single ──────────────────────────────────────────────────
  function handleShare(doc: VaultDocument) {
    router.push(`/(vault)/vault/document-viewer?id=${doc.id}&action=share`);
  }

  // ── View ──────────────────────────────────────────────────────────
  function handleView(doc: VaultDocument) {
    router.push(`/(vault)/vault/document-viewer?id=${doc.id}`);
  }

  const totalDocs = allDocuments.length;

  return (
    <View style={s.screen}>
      {menuVisible && <MenuPanel visible onClose={() => setMenuVisible(false)} />}
      {bellVisible && (
        <BellPopup
          onClose={() => { setBellVisible(false); setBellBadge(0); }}
          onTap={() => {
            setBellVisible(false); setBellBadge(0);
            handleView(allDocuments.find(d => d.id === NOTIFICATION.documentId) ?? allDocuments[0]);
          }}
        />
      )}
      <CompanyPicker
        visible={companyPickerVisible}
        selected={companyFilter}
        onSelect={setCompanyFilter}
        onClose={() => setCompanyPickerVisible(false)}
        totalDocs={totalDocs}
        emailCount={emailCount}
        selfCount={selfCount}
        employers={employersWithCounts}
      />
      <DocTypePicker
        visible={docTypePickerVisible}
        selected={docTypeFilter}
        companyFilter={companyFilter}
        onSelect={setDocTypeFilter}
        onClose={() => setDocTypePickerVisible(false)}
        documents={allDocuments}
      />
      <ZipModal
        visible={zipVisible}
        count={selectedIds.size}
        onDone={handleZipDownload}
      />

      {/* ── Dark gradient header ── */}
      <LinearGradient
        colors={gradTopBg.colors}
        locations={gradTopBg.locations}
        start={gradTopBg.start}
        end={gradTopBg.end}
        style={s.topBg}
      >
        <View style={s.orbTR} pointerEvents="none" />
        <SafeAreaView edges={['top']}>
          <View style={s.headerRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.greeting}>
                {profile?.name ? `${profile.name.split(' ')[0]}'s vault` : 'My vault'}
              </Text>
              <Text style={s.vaultMeta}>
                {docsLoading ? 'Loading…' : `${totalDocs} documents  ·  ${employers.length} employer${employers.length === 1 ? '' : 's'}`}
              </Text>
            </View>
            <View style={s.headerActions}>
              <Pressable style={s.headerBtn} onPress={() => bellBadge > 0 && setBellVisible(true)}>
                <Text style={s.headerBtnIcon}>🔔</Text>
                {bellBadge > 0 && (
                  <View style={s.bellBadge}><Text style={s.bellBadgeText}>{bellBadge}</Text></View>
                )}
              </Pressable>
              <Pressable style={s.headerBtn} onPress={() => router.push('/(vault)/vault/self-upload')}>
                <Text style={s.headerBtnIcon}>⬆</Text>
              </Pressable>
              <Pressable style={s.headerBtn} onPress={() => setMenuVisible(true)}>
                <Text style={s.headerBtnIcon}>☰</Text>
              </Pressable>
            </View>
          </View>
        </SafeAreaView>
      </LinearGradient>

      {/* ── Filter bar ── */}
      <View style={s.filterBar}>
        <Pressable
          style={[s.filterBtn, companyFilter !== 'ALL' && s.filterBtnActive]}
          onPress={() => setCompanyPickerVisible(true)}
        >
          <Text style={s.filterBtnIcon}>
            {companyFilter === 'SELF' ? '⬆' : companyFilter === 'EMAIL' ? '📧' : '🏢'}
          </Text>
          <Text style={[s.filterBtnText, companyFilter !== 'ALL' && s.filterBtnTextActive]} numberOfLines={1}>
            {companyLabel}
          </Text>
          <Text style={[s.filterChevron, companyFilter !== 'ALL' && s.filterBtnTextActive]}>▾</Text>
        </Pressable>

        <Pressable
          style={[s.filterBtn, docTypeFilter !== 'ALL' && s.filterBtnActive]}
          onPress={() => setDocTypePickerVisible(true)}
        >
          <Text style={s.filterBtnIcon}>📄</Text>
          <Text style={[s.filterBtnText, docTypeFilter !== 'ALL' && s.filterBtnTextActive]} numberOfLines={1}>
            {docTypeLabel}
          </Text>
          <Text style={[s.filterChevron, docTypeFilter !== 'ALL' && s.filterBtnTextActive]}>▾</Text>
        </Pressable>
      </View>

      {/* ── Body ── */}
      {docsLoading ? (
        <View style={s.loadingState}>
          <ActivityIndicator size="large" color={colors.indigo} />
          <Text style={s.loadingText}>Loading your vault…</Text>
        </View>
      ) : totalDocs === 0 ? (
        <EmptyVaultState />
      ) : (
        <ScrollView
          style={s.body}
          contentContainerStyle={s.bodyContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Stat row */}
          <View style={s.statRow}>
            <StatCard value={filteredDocs.length} label="Documents"    accent="indigo" />
            <StatCard value={activeSharesCount}   label="Active shares" accent="emerald" />
          </View>

          {/* Benchmarking nudge — shown once when salary slip is ready but not yet opted in */}
          {showBenchNudge && (
            <View style={s.benchNudge}>
              <Text style={s.benchNudgeIcon}>📈</Text>
              <View style={{ flex: 1 }}>
                <Text style={s.benchNudgeTitle}>See how your comp compares</Text>
                <Text style={s.benchNudgeSub}>
                  Your salary slip is ready. Opt in to see your anonymous market percentile.
                </Text>
                <Pressable
                  style={s.benchNudgeBtn}
                  onPress={() => { dismissNudge(); router.push('/(vault)/benchmarking' as any); }}
                >
                  <Text style={s.benchNudgeBtnText}>Comp Benchmark →</Text>
                </Pressable>
              </View>
              <Pressable onPress={dismissNudge} style={s.benchNudgeClose}>
                <Text style={s.benchNudgeCloseText}>✕</Text>
              </Pressable>
            </View>
          )}

          {/* Source legend when showing all */}
          {companyFilter === 'ALL' && <SourceLegend />}

          {filteredDocs.length === 0 ? (
            <View style={s.noResults}>
              <Text style={s.noResultsIcon}>🔍</Text>
              <Text style={s.noResultsTitle}>No documents match</Text>
              <Text style={s.noResultsSub}>Try a different company or document type.</Text>
              <Pressable style={s.clearBtn} onPress={() => { setCompanyFilter('ALL'); setDocTypeFilter('ALL'); }}>
                <Text style={s.clearBtnText}>Clear filters</Text>
              </Pressable>
            </View>
          ) : (
            <>
              <SectionHeader
                label={sectionLabel}
                count={filteredDocs.length}
                selectionMode={selectionMode}
                allSelected={allFilteredSelected}
                onSelectAll={toggleSelectAll}
              />
              {filteredDocs.map(doc => (
                <DocumentCard
                  key={doc.id}
                  id={doc.id}
                  iconType={doc.icon_type as any}
                  iconEmoji={doc.icon_emoji}
                  title={doc.title}
                  issuer={doc.issuer}
                  docType={DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}
                  sourceType={doc.source_type as any}
                  receivedAt={doc.received_at}
                  highlighted={doc.id === NOTIFICATION.documentId && bellBadge > 0}
                  selectionMode={selectionMode}
                  selected={selectedIds.has(doc.id)}
                  onPress={() => toggleSelect(doc.id)}
                  onLongPress={() => enterSelection(doc.id)}
                  onView={() => handleView(doc)}
                  onDownload={() => handleDownload(doc)}
                  onShare={() => handleShare(doc)}
                />
              ))}
            </>
          )}
        </ScrollView>
      )}

      {/* ── Multi-select action bar ── */}
      {selectionMode && (
        <View style={s.selectionBar}>
          <Pressable style={s.selectionCancel} onPress={cancelSelection}>
            <Text style={s.selectionCancelText}>✕</Text>
          </Pressable>
          <Text style={s.selectionCount}>{selectedIds.size} selected</Text>
          <Pressable
            style={[s.zipBtn, selectedIds.size === 0 && s.zipBtnDim]}
            onPress={selectedIds.size > 0 ? () => setZipVisible(true) : undefined}
          >
            <LinearGradient
              colors={gradJourney.colors}
              locations={gradJourney.locations}
              start={gradJourney.start}
              end={gradJourney.end}
              style={s.zipGrad}
            >
              {zipLoading
                ? <ActivityIndicator size="small" color="#04261C" />
                : <Text style={s.zipText}>⬇  Download ZIP ({selectedIds.size})</Text>
              }
            </LinearGradient>
          </Pressable>
        </View>
      )}

      <VaultNav active="vault" onPress={(key) => {
        if (key === 'activity') router.push('/(vault)/activity');
        else if (key === 'career') router.push('/(vault)/career');
        else if (key === 'shares') router.push('/(vault)/shares');
        else if (key === 'settings') router.push('/(vault)/settings');
      }} />
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },

  // Header
  topBg: { paddingHorizontal: 20, paddingBottom: 14, overflow: 'hidden' },
  orbTR: { position: 'absolute', width: 220, height: 220, borderRadius: 110, backgroundColor: colors.indigo, opacity: 0.16, top: -70, right: -70 },
  headerRow: { flexDirection: 'row', alignItems: 'center', paddingTop: 10, paddingBottom: 4, gap: 10 },
  greeting: { fontFamily: fonts.displayBold, fontSize: 20, color: '#FFFFFF', letterSpacing: -0.3 },
  vaultMeta: { fontFamily: fonts.mono, fontSize: 10, color: '#9CA8C9', marginTop: 3 },
  headerActions: { flexDirection: 'row', gap: 6 },
  headerBtn: { width: 32, height: 32, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)', alignItems: 'center', justifyContent: 'center' },
  headerBtnIcon: { fontSize: 14, color: '#FFFFFF' },
  bellBadge: { position: 'absolute', top: -4, right: -4, minWidth: 16, height: 16, borderRadius: 8, backgroundColor: colors.rose, borderWidth: 1.5, borderColor: colors.space, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 2 },
  bellBadgeText: { fontFamily: fonts.mono, fontSize: 9, color: '#FFFFFF', fontWeight: '700' },

  // Filter bar
  filterBar: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.surface3, backgroundColor: colors.surface },
  filterBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface3, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: colors.surface3 },
  filterBtnActive: { backgroundColor: 'rgba(99,102,241,0.08)', borderColor: colors.indigo },
  filterBtnIcon: { fontSize: 13 },
  filterBtnText: { flex: 1, fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.ink2 },
  filterBtnTextActive: { color: colors.indigo },
  filterChevron: { fontSize: 10, color: colors.ink3 },

  // Loading
  loadingState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, paddingBottom: 100 },
  loadingText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.ink3 },

  // Body
  body: { flex: 1 },
  bodyContent: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 140 },
  statRow: { flexDirection: 'row', gap: 11, marginBottom: 16 },

  // No results
  noResults: { alignItems: 'center', paddingTop: 48, gap: 8 },
  noResultsIcon: { fontSize: 36 },
  noResultsTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.ink },
  noResultsSub: { fontSize: 13, color: colors.ink3, textAlign: 'center' },
  clearBtn: { marginTop: 8, paddingHorizontal: 20, paddingVertical: 9, backgroundColor: colors.surface3, borderRadius: 20 },
  clearBtnText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo },

  // Benchmarking nudge
  benchNudge: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
    backgroundColor: '#EFF6FF', borderRadius: 14, padding: 14,
    borderWidth: 1, borderColor: '#BFDBFE', marginBottom: 4,
  },
  benchNudgeIcon: { fontSize: 22, marginTop: 1 },
  benchNudgeTitle: { fontSize: 13, fontFamily: fonts.bodySemiBold, color: '#1E40AF', marginBottom: 2 },
  benchNudgeSub:   { fontSize: 12, color: '#3B82F6', lineHeight: 17, marginBottom: 8 },
  benchNudgeBtn:   { alignSelf: 'flex-start', backgroundColor: '#2563EB', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6 },
  benchNudgeBtnText: { fontSize: 12, fontFamily: fonts.bodySemiBold, color: '#FFFFFF' },
  benchNudgeClose: { padding: 4 },
  benchNudgeCloseText: { fontSize: 14, color: '#93C5FD' },

  // Multi-select bar
  selectionBar: {
    position: 'absolute', bottom: 86, left: 16, right: 16,
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.space, borderRadius: 20, padding: 10,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.10)',
    shadowColor: '#000', shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.45, shadowRadius: 18, elevation: 14,
  },
  selectionCancel: { width: 32, height: 32, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.07)', alignItems: 'center', justifyContent: 'center' },
  selectionCancelText: { fontSize: 13, color: '#9CA8C9' },
  selectionCount: { fontFamily: fonts.displayBold, fontSize: 14, color: '#FFFFFF', flex: 1, textAlign: 'center' },
  zipBtn: {},
  zipBtnDim: { opacity: 0.4 },
  zipGrad: { borderRadius: 12, paddingHorizontal: 14, paddingVertical: 9, minWidth: 80, alignItems: 'center' },
  zipText: { fontFamily: fonts.displayBold, fontSize: 13, color: '#04261C' },
});
