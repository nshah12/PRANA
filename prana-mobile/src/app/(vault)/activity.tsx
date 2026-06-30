import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, Modal, ScrollView, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { tUi } from '@/i18n';

// ── API types ─────────────────────────────────────────────────────
interface PipelineDoc {
  id: string;
  doc_title: string;
  employer: string;
  pushed_at: string;
  status: 'routed' | 'pending_password' | 'exception' | 'processing';
  resolution_method?: string;
  routed_at?: string;
  privacy_note: string;
}

interface PipelinePush {
  id: string;
  employer: string;
  doc_count: number;
  pushed_at: string;
  unread: boolean;
  docs: PipelineDoc[];
}

// ── Helpers ───────────────────────────────────────────────────────
function fmt(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    + ' · '
    + d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

function relativeDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

const RESOLUTION_LABEL: Record<string, string> = {
  PAN_TOKEN_EXACT: 'Matched via PAN token',
  EMP_ID: 'Matched via Employee ID',
  FUZZY: 'Matched via name + DOJ',
  EMBEDDING: 'Matched via embedding',
};

const STATUS_COLOR: Record<string, string> = {
  routed: colors.emerald,
  pending_password: colors.amber,
  exception: colors.rose,
  processing: colors.cyan,
};

const STATUS_LABEL: Record<string, string> = {
  routed: '✓ Routed to vault',
  pending_password: '🔐 Awaiting password',
  exception: '⚠ Needs attention',
  processing: '⟳ Processing',
};

// ── Doc detail bottom sheet ───────────────────────────────────────
function DocDetailSheet({
  doc, onClose,
}: { doc: PipelineDoc; onClose: () => void }) {
  return (
    <Modal visible animationType="slide" transparent>
      <View style={styles.sheetOverlay}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.sheetHandle} />

          <View style={styles.sheetHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.sheetDocTitle}>{doc.doc_title}</Text>
              <View style={styles.sheetEmployerRow}>
                <View style={styles.employerBadge}>
                  <Text style={styles.employerBadgeText}>{doc.employer}</Text>
                </View>
                <Text style={styles.sheetTime}>{fmt(doc.pushed_at)}</Text>
              </View>
            </View>
          </View>

          {/* Pipeline stages */}
          <Text style={styles.sheetSection}>PIPELINE TRACE</Text>
          <View style={styles.pipelineTrace}>
            {[
              { label: 'Received from employer', done: true, note: fmt(doc.pushed_at) },
              { label: 'PAN encrypted at boundary', done: doc.status !== 'pending_password', note: 'HMAC token + FF3-1 FPE · Plaintext discarded' },
              { label: 'Processed by LLM', done: doc.status === 'routed', note: 'NIK-redacted document · Insights extracted' },
              { label: 'Identity resolved', done: doc.status === 'routed', note: doc.resolution_method ? RESOLUTION_LABEL[doc.resolution_method] : '—' },
              { label: 'Routed to your vault', done: doc.status === 'routed', note: doc.routed_at ? fmt(doc.routed_at) : '—' },
            ].map((step, i) => (
              <View key={i} style={styles.traceRow}>
                <View style={styles.traceLeft}>
                  <View style={[styles.traceDot, step.done ? styles.traceDotDone : styles.traceDotPending]} />
                  {i < 4 && <View style={[styles.traceLine, step.done && styles.traceLineDone]} />}
                </View>
                <View style={styles.traceBody}>
                  <Text style={[styles.traceLabel, !step.done && styles.traceLabelDim]}>{step.label}</Text>
                  <Text style={styles.traceNote}>{step.note}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Privacy note */}
          <View style={styles.privacyNote}>
            <Text style={styles.privacyNoteText}>🔒 {doc.privacy_note}</Text>
          </View>

          {/* CTA for password-protected */}
          {doc.status === 'pending_password' && (
            <Pressable
              style={styles.unlockCta}
              onPress={() => {
                onClose();
                router.push({
                  pathname: '/(vault)/vault/unlock-document',
                  params: { docTitle: doc.doc_title, employer: doc.employer },
                });
              }}
            >
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.unlockCtaGrad}>
                <Text style={styles.unlockCtaText}>🔐 Unlock &amp; Process →</Text>
              </LinearGradient>
            </Pressable>
          )}

          <Pressable style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>Close</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

// ── Push card ─────────────────────────────────────────────────────
function PushCard({ push }: { push: PipelinePush }) {
  const [expanded, setExpanded] = useState(push.unread);
  const [selectedDoc, setSelectedDoc] = useState<PipelineDoc | null>(null);

  const pendingCount = push.docs.filter(d => d.status === 'pending_password').length;
  const routedCount = push.docs.filter(d => d.status === 'routed').length;

  return (
    <View style={[styles.pushCard, push.unread && styles.pushCardUnread]}>
      {/* Push header */}
      <Pressable style={styles.pushHeader} onPress={() => setExpanded(v => !v)}>
        <View style={styles.pushIconWrap}>
          <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.pushIcon}>
            <Text style={{ fontSize: 14, color: '#04261C' }}>📥</Text>
          </LinearGradient>
        </View>
        <View style={{ flex: 1 }}>
          <View style={styles.pushTitleRow}>
            <Text style={styles.pushEmployer}>{push.employer}</Text>
            {push.unread && <View style={styles.unreadDot} />}
            {pendingCount > 0 && (
              <View style={styles.pendingBadge}>
                <Text style={styles.pendingBadgeText}>🔐 {pendingCount} awaiting</Text>
              </View>
            )}
          </View>
          <Text style={styles.pushSub}>
            Pushed {push.doc_count} document{push.doc_count > 1 ? 's' : ''} · {relativeDate(push.pushed_at)}
          </Text>
          <Text style={styles.pushStats}>
            {routedCount === push.doc_count
              ? `✓ All ${push.doc_count} routed to vault`
              : `${routedCount}/${push.doc_count} routed · ${pendingCount} pending`}
          </Text>
        </View>
        <Text style={[styles.chevron, expanded && styles.chevronOpen]}>›</Text>
      </Pressable>

      {/* Expanded doc list */}
      {expanded && (
        <View style={styles.docList}>
          {push.docs.map(doc => (
            <Pressable
              key={doc.id}
              style={styles.docRow}
              onPress={() => setSelectedDoc(doc)}
            >
              <View style={[styles.docStatusDot, { backgroundColor: STATUS_COLOR[doc.status] }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.docRowTitle}>{doc.doc_title}</Text>
                <Text style={[styles.docRowStatus, { color: STATUS_COLOR[doc.status] }]}>
                  {STATUS_LABEL[doc.status]}
                </Text>
              </View>
              <Text style={styles.docRowArrow}>›</Text>
            </Pressable>
          ))}

          <View style={styles.pipelineFooter}>
            <Text style={styles.pipelineFooterText}>
              🔒 Processed in-memory · PAN encrypted · Raw data discarded
            </Text>
          </View>
        </View>
      )}

      {selectedDoc && (
        <DocDetailSheet doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </View>
  );
}

// ── Screen ────────────────────────────────────────────────────────
export default function ActivityScreen() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['vault', 'activity'],
    queryFn: () => api.get<{
      access_log: Array<{ id: string; action: string; doc_title: string; occurred_at: string }>;
      pipeline_pushes: PipelinePush[];
    }>('/vault/activity'),
  });

  const pushes = data?.pipeline_pushes ?? [];
  const accessLog = data?.access_log ?? [];
  const unreadCount = pushes.filter(p => p.unread).length;

  return (
    <View style={styles.screen}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>Activity</Text>
            <Text style={styles.headerSub}>Documents, pipeline &amp; login history</Text>
          </View>
          {unreadCount > 0 && (
            <View style={styles.unreadBadge}>
              <Text style={styles.unreadBadgeText}>{unreadCount} new</Text>
            </View>
          )}
        </View>
      </SafeAreaView>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontFamily: fonts.mono, fontSize: 12, color: colors.ink3 }}>Loading activity…</Text>
        </View>
      ) : isError ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 }}>
          <Text style={{ fontFamily: fonts.mono, fontSize: 12, color: colors.rose }}>{tUi('ACTIVITY_LOAD_FAILED')}</Text>
          <Pressable onPress={() => refetch()} style={{ padding: 10 }}>
            <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.indigo }}>{tUi('RETRY')}</Text>
          </Pressable>
        </View>
      ) : (
        <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent} showsVerticalScrollIndicator={false}>

          {/* ── PIPELINE INBOX ── */}
          <Text style={styles.sectionLabel}>PIPELINE INBOX</Text>
          <Text style={styles.sectionNote}>
            Every document your employer pushes passes through PRANA's 6-stage pipeline. Track what happened to each one.
          </Text>
          {pushes.length === 0 ? (
            <View style={[styles.listCard, { padding: 20, alignItems: 'center' }]}>
              <Text style={{ fontFamily: fonts.mono, fontSize: 12, color: colors.ink3 }}>No documents yet</Text>
            </View>
          ) : (
            pushes.map(push => <PushCard key={push.id} push={push} />)
          )}

          {/* ── DOCUMENT ACCESS ── */}
          {accessLog.length > 0 && (
            <>
              <Text style={[styles.sectionLabel, { marginTop: 8 }]}>DOCUMENT ACCESS</Text>
              <View style={styles.listCard}>
                {accessLog.map((a, i) => (
                  <View key={a.id} style={[styles.listRow, i === accessLog.length - 1 && styles.listRowLast]}>
                    <View style={[styles.listDot, { backgroundColor: colors.indigo }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.listText}>{a.action}</Text>
                      <Text style={styles.listSub}>{a.doc_title}</Text>
                    </View>
                    <Text style={styles.listTime}>{fmt(a.occurred_at)}</Text>
                  </View>
                ))}
              </View>
            </>
          )}

        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  safeArea: { backgroundColor: colors.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 16,
    borderBottomWidth: 1, borderBottomColor: colors.surface3,
  },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink, letterSpacing: -0.3 },
  headerSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 3 },
  unreadBadge: {
    backgroundColor: colors.indigo, borderRadius: 20,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  unreadBadgeText: { fontFamily: fonts.mono, fontSize: 11, color: '#FFFFFF', fontWeight: '700' },

  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 100, gap: 8 },

  sectionLabel: {
    fontFamily: fonts.mono, fontSize: 10, color: colors.ink3,
    letterSpacing: 1.2, textTransform: 'uppercase', paddingLeft: 4,
  },
  sectionNote: {
    fontSize: 12, color: colors.ink3, lineHeight: 18, paddingLeft: 4, marginBottom: 4,
  },

  // Push card
  pushCard: {
    backgroundColor: colors.surface3,
    borderRadius: 18,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  pushCardUnread: {
    borderColor: 'rgba(99,102,241,0.3)',
    backgroundColor: 'rgba(99,102,241,0.04)',
  },
  pushHeader: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14,
  },
  pushIconWrap: { paddingTop: 2 },
  pushIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  pushTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 },
  pushEmployer: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink },
  unreadDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.indigo },
  pendingBadge: {
    backgroundColor: 'rgba(251,191,36,0.15)',
    borderWidth: 1, borderColor: 'rgba(251,191,36,0.3)',
    borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2,
  },
  pendingBadgeText: { fontFamily: fonts.mono, fontSize: 9, color: colors.amber },
  pushSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginBottom: 2 },
  pushStats: { fontSize: 11, color: colors.ink2 },
  chevron: { fontSize: 22, color: colors.ink3, marginTop: 4 },
  chevronOpen: { transform: [{ rotate: '90deg' }] },

  docList: { borderTopWidth: 1, borderTopColor: 'rgba(0,0,0,0.06)' },
  docRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  docStatusDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  docRowTitle: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.ink, marginBottom: 2 },
  docRowStatus: { fontFamily: fonts.mono, fontSize: 10 },
  docRowArrow: { fontSize: 18, color: colors.ink3 },

  pipelineFooter: {
    paddingHorizontal: 14, paddingVertical: 10,
    backgroundColor: 'rgba(52,211,153,0.06)',
  },
  pipelineFooterText: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, textAlign: 'center' },

  // Generic list card (access, login)
  listCard: { backgroundColor: colors.surface3, borderRadius: 18, overflow: 'hidden' },
  listRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  listRowLast: { borderBottomWidth: 0 },
  listDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  listText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.ink },
  listSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  listTime: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },

  // Doc detail sheet
  sheetOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface2,
    borderTopLeftRadius: 28, borderTopRightRadius: 28,
    padding: 20, paddingBottom: 36,
    maxHeight: '85%',
  },
  sheetHandle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: colors.surface3, alignSelf: 'center', marginBottom: 20,
  },
  sheetHeader: { marginBottom: 16 },
  sheetDocTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.ink, marginBottom: 8 },
  sheetEmployerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  employerBadge: {
    backgroundColor: 'rgba(52,211,153,0.12)',
    borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3,
  },
  employerBadgeText: { fontFamily: fonts.mono, fontSize: 10, color: '#047857' },
  sheetTime: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },

  sheetSection: {
    fontFamily: fonts.mono, fontSize: 10, color: colors.ink3,
    letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 14,
  },

  // Pipeline trace
  pipelineTrace: { marginBottom: 16 },
  traceRow: { flexDirection: 'row', gap: 12, minHeight: 44 },
  traceLeft: { alignItems: 'center', width: 16 },
  traceDot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2, marginTop: 3 },
  traceDotDone: { borderColor: colors.emerald, backgroundColor: 'rgba(52,211,153,0.2)' },
  traceDotPending: { borderColor: colors.ink3, backgroundColor: 'transparent' },
  traceLine: { width: 2, flex: 1, backgroundColor: 'rgba(0,0,0,0.08)', marginTop: 2 },
  traceLineDone: { backgroundColor: 'rgba(52,211,153,0.3)' },
  traceBody: { flex: 1, paddingBottom: 12 },
  traceLabel: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.ink, marginBottom: 3 },
  traceLabelDim: { color: colors.ink3 },
  traceNote: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, lineHeight: 16 },

  privacyNote: {
    backgroundColor: 'rgba(52,211,153,0.08)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.2)',
    borderRadius: 12, padding: 12, marginBottom: 14,
  },
  privacyNoteText: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink2, lineHeight: 17 },

  unlockCta: { marginBottom: 10 },
  unlockCtaGrad: { borderRadius: 14 },
  unlockCtaText: {
    fontFamily: fonts.displayBold, fontSize: 14, color: '#04261C',
    textAlign: 'center', padding: 14,
  },

  closeBtn: {
    borderWidth: 1, borderColor: colors.surface3,
    borderRadius: 14, paddingVertical: 12, alignItems: 'center',
  },
  closeBtnText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink2 },
});
