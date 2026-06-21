import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, Modal, ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ── Confirmation modal ────────────────────────────────────────────
function ConfirmModal({
  visible, title, body, confirmLabel, confirmDanger,
  onConfirm, onCancel,
}: {
  visible: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  confirmDanger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={styles.modalOverlay}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onCancel} />
        <View style={styles.modalCard}>
          <Text style={styles.modalTitle}>{title}</Text>
          <Text style={styles.modalBody}>{body}</Text>
          <View style={styles.modalBtns}>
            <Pressable style={styles.modalCancel} onPress={onCancel}>
              <Text style={styles.modalCancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[styles.modalConfirm, confirmDanger && styles.modalConfirmDanger]}
              onPress={onConfirm}
            >
              <Text style={[styles.modalConfirmText, confirmDanger && styles.modalConfirmTextDanger]}>
                {confirmLabel}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

// ── Success modal ─────────────────────────────────────────────────
function SuccessModal({ visible, title, sub, onClose }: {
  visible: boolean; title: string; sub: string; onClose: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={styles.modalOverlay}>
        <View style={styles.modalCard}>
          <View style={styles.successOrb}>
            <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.successGrad}>
              <Text style={{ fontSize: 24 }}>✓</Text>
            </LinearGradient>
          </View>
          <Text style={styles.modalTitle}>{title}</Text>
          <Text style={styles.modalBody}>{sub}</Text>
          <Pressable style={styles.successBtn} onPress={onClose}>
            <Text style={styles.successBtnText}>Done</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

// ── Right card ────────────────────────────────────────────────────
function RightCard({
  icon, iconBg, title, sub, actionLabel, actionColor, onAction, tag,
}: {
  icon: string;
  iconBg: string;
  title: string;
  sub: string;
  actionLabel: string;
  actionColor?: string;
  onAction: () => void;
  tag?: string;
}) {
  return (
    <View style={styles.rightCard}>
      <View style={styles.rightCardTop}>
        <View style={[styles.rightIcon, { backgroundColor: iconBg }]}>
          <Text style={{ fontSize: 18 }}>{icon}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <View style={styles.titleRow}>
            <Text style={styles.rightTitle}>{title}</Text>
            {tag ? <View style={styles.tagBadge}><Text style={styles.tagText}>{tag}</Text></View> : null}
          </View>
          <Text style={styles.rightSub}>{sub}</Text>
        </View>
      </View>
      <Pressable
        style={[styles.actionBtn, actionColor === 'danger' && styles.actionBtnDanger]}
        onPress={onAction}
      >
        <Text style={[styles.actionText, actionColor === 'danger' && styles.actionTextDanger]}>
          {actionLabel}
        </Text>
      </Pressable>
    </View>
  );
}

// ── Screen ────────────────────────────────────────────────────────
type ActiveModal = 'download' | 'erasure' | 'withdraw' | null;
type ActiveSuccess = 'download' | 'erasure' | 'withdraw' | null;

export default function DataRightsScreen() {
  const [confirmModal, setConfirmModal] = useState<ActiveModal>(null);
  const [successModal, setSuccessModal] = useState<ActiveSuccess>(null);
  const queryClient = useQueryClient();

  const { data: consentData } = useQuery({
    queryKey: ['compliance', 'consent'],
    queryFn: () => api.get<{ status: string; granted_at: string | null }>('/vault/compliance/consent'),
  });

  const { data: vaultData } = useQuery({
    queryKey: ['vault', 'summary'],
    queryFn: () => api.get<{ doc_count: number }>('/vault/documents?limit=0'),
    select: (d: any) => ({ doc_count: d?.total ?? 0 }),
  });

  const exportMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/export'),
    onSuccess: () => { setConfirmModal(null); setTimeout(() => setSuccessModal('download'), 300); },
  });

  const erasureMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/erasure'),
    onSuccess: () => { setConfirmModal(null); setTimeout(() => setSuccessModal('erasure'), 300); },
  });

  const withdrawMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/consent/withdraw'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance', 'consent'] });
      setConfirmModal(null);
      setTimeout(() => setSuccessModal('withdraw'), 300);
    },
  });

  function handleConfirm(type: ActiveModal) {
    if (type === 'download') exportMutation.mutate();
    else if (type === 'erasure') erasureMutation.mutate();
    else if (type === 'withdraw') withdrawMutation.mutate();
  }

  const isConsented = !consentData || consentData.status === 'ACTIVE';
  const docCount = vaultData?.doc_count ?? 0;

  const MODAL_CONTENT: Record<string, { title: string; body: string; label: string; danger?: boolean }> = {
    download: {
      title: 'Download your data',
      body: `We will prepare a ZIP containing your vault index, document metadata, career events, and activity log. Raw salary figures are not included — only the metadata we store.\n\nThe download link will be sent to your registered mobile number.`,
      label: 'Request download',
    },
    erasure: {
      title: 'Request account deletion',
      body: 'This will permanently delete your PRANA account, all stored metadata, embeddings, career insights, and activity logs. Your documents with employers are not affected — they remain with the employer.\n\nThis action cannot be undone.',
      label: 'Delete my account',
      danger: true,
    },
    withdraw: {
      title: 'Withdraw consent',
      body: 'Withdrawing consent will stop PRANA from processing any new documents pushed by your employers. Existing documents in your vault will remain until you request erasure.\n\nYou can re-consent at any time from this screen.',
      label: 'Withdraw consent',
      danger: true,
    },
  };

  const SUCCESS_CONTENT: Record<string, { title: string; sub: string }> = {
    download: {
      title: 'Request submitted',
      sub: 'Your data export will be ready within 24 hours. A download link will be sent to your registered mobile number.',
    },
    erasure: {
      title: 'Deletion requested',
      sub: 'Your account deletion request has been logged. All data will be permanently erased within 30 days as required by DPDP Act 2023.',
    },
    withdraw: {
      title: 'Consent withdrawn',
      sub: 'PRANA will no longer process new documents from your employers. You can re-consent at any time from this screen.',
    },
  };

  return (
    <View style={styles.screen}>
      <SafeAreaView edges={['top']} style={styles.safe}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Text style={styles.backText}>‹</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerTitle}>My Data Rights</Text>
            <Text style={styles.headerSub}>DPDP Act 2023 · Your rights over your data</Text>
          </View>
          <View style={styles.dpdpBadge}>
            <Text style={styles.dpdpText}>⚖️ DPDP</Text>
          </View>
        </View>
      </SafeAreaView>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent} showsVerticalScrollIndicator={false}>

        {/* Data snapshot */}
        <View style={styles.snapshotCard}>
          <Text style={styles.snapshotTitle}>What PRANA stores for you</Text>
          <View style={styles.snapshotGrid}>
            {[
              ['Documents', `${docCount}`],
              ['Metadata only', 'No raw ₹'],
              ['PAN stored', 'Encrypted'],
              ['Insights', 'Indices only'],
            ].map(([label, val]) => (
              <View key={label} style={styles.snapshotCell}>
                <Text style={styles.snapshotVal}>{val}</Text>
                <Text style={styles.snapshotLabel}>{label}</Text>
              </View>
            ))}
          </View>
          <Text style={styles.snapshotNote}>
            Raw salary figures are processed in-memory and discarded. Only growth indices and consistency verdicts are stored.
          </Text>
        </View>

        {/* Consent status */}
        <View style={[styles.consentBanner, !isConsented && styles.consentBannerWithdrawn]}>
          <View style={[styles.consentDot, !isConsented && styles.consentDotWithdrawn]} />
          <View style={{ flex: 1 }}>
            <Text style={styles.consentTitle}>{isConsented ? 'Consent active' : 'Consent withdrawn'}</Text>
            <Text style={styles.consentSub}>
              {isConsented
                ? `Granted · DPDP v1 · ${consentData?.granted_at ? new Date(consentData.granted_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}`
                : 'Re-grant consent to allow document processing'}
            </Text>
          </View>
          {isConsented
            ? <Text style={styles.consentCheck}>✓</Text>
            : (
              <Pressable
                onPress={() => api.post('/vault/compliance/consent/grant').then(() => queryClient.invalidateQueries({ queryKey: ['compliance', 'consent'] }))}
                style={{ paddingHorizontal: 10, paddingVertical: 6, backgroundColor: 'rgba(52,211,153,0.15)', borderRadius: 10 }}
              >
                <Text style={{ fontFamily: fonts.mono, fontSize: 10, color: colors.emerald }}>Re-grant</Text>
              </Pressable>
            )
          }
        </View>

        {/* Rights */}
        <Text style={styles.sectionLabel}>YOUR RIGHTS</Text>

        <RightCard
          icon="📥"
          iconBg="rgba(99,102,241,0.12)"
          title="Right to access"
          sub="Download all data PRANA holds about you — document index, career events, activity log, stored metadata. Delivered as a ZIP to your registered number."
          actionLabel="Request data download"
          onAction={() => setConfirmModal('download')}
          tag="DPDP §11"
        />

        <RightCard
          icon="✏️"
          iconBg="rgba(34,211,238,0.12)"
          title="Right to correction"
          sub="Dispute a document that was wrongly attributed to your vault. Flag it from the document viewer and an OA will review within 24 hours."
          actionLabel="Go to vault to flag a document →"
          onAction={() => router.push('/(vault)/vault')}
          tag="DPDP §12"
        />

        <RightCard
          icon="🗑"
          iconBg="rgba(251,113,133,0.10)"
          title="Right to erasure"
          sub="Permanently delete your PRANA account, all metadata, embeddings, and activity logs. Your employer documents are unaffected."
          actionLabel="Request account deletion"
          actionColor="danger"
          onAction={() => setConfirmModal('erasure')}
          tag="DPDP §13"
        />

        <RightCard
          icon="🚫"
          iconBg="rgba(251,191,36,0.10)"
          title="Right to withdraw consent"
          sub="Stop PRANA from processing any future documents. Existing vault data is retained until you request erasure."
          actionLabel="Withdraw consent"
          actionColor="danger"
          onAction={() => setConfirmModal('withdraw')}
          tag="DPDP §6"
        />

        <RightCard
          icon="📋"
          iconBg="rgba(99,102,241,0.10)"
          title="Right to grievance redressal"
          sub="Raise a concern about unauthorised access, data misuse, or delayed response. Our DPDP officer responds within 7 business days."
          actionLabel="Go to Privacy Cockpit →"
          onAction={() => router.push('/(vault)/privacy' as any)}
          tag="DPDP §14"
        />

        <RightCard
          icon="👨‍👩‍👧"
          iconBg="rgba(52,211,153,0.10)"
          title="Nominate a guardian"
          sub="Designate a trusted person to manage your vault on your behalf — for minors or in case of incapacitation."
          actionLabel="Manage nominations →"
          onAction={() => router.push('/(vault)/nomination' as any)}
          tag="DPDP §15"
        />

        {/* Privacy cockpit link */}
        <View style={styles.grievanceCard}>
          <Text style={styles.grievanceTitle}>🔍 Privacy Cockpit</Text>
          <Text style={styles.grievanceText}>
            See exactly who accessed your documents, AI processing logs, and file a formal grievance.{' '}
            <Text style={styles.grievanceEmail} onPress={() => router.push('/(vault)/privacy' as any)}>Open Privacy Cockpit →</Text>
          </Text>
        </View>

      </ScrollView>

      {/* Confirm modals */}
      {(['download', 'erasure', 'withdraw'] as const).map(type => (
        <ConfirmModal
          key={type}
          visible={confirmModal === type}
          title={MODAL_CONTENT[type].title}
          body={MODAL_CONTENT[type].body}
          confirmLabel={MODAL_CONTENT[type].label}
          confirmDanger={MODAL_CONTENT[type].danger}
          onConfirm={() => handleConfirm(type)}
          onCancel={() => setConfirmModal(null)}
        />
      ))}

      {/* Success modals */}
      {(['download', 'erasure', 'withdraw'] as const).map(type => (
        <SuccessModal
          key={type}
          visible={successModal === type}
          title={SUCCESS_CONTENT[type].title}
          sub={SUCCESS_CONTENT[type].sub}
          onClose={() => { setSuccessModal(null); if (type !== 'download') router.replace('/(auth)/sign-in'); }}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  safe: { backgroundColor: colors.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: colors.surface3,
  },
  backBtn: { padding: 4, marginRight: 2 },
  backText: { fontSize: 28, color: colors.ink2, lineHeight: 32 },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: colors.ink },
  headerSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  dpdpBadge: {
    backgroundColor: 'rgba(99,102,241,0.10)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.2)',
    borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4,
  },
  dpdpText: { fontFamily: fonts.mono, fontSize: 10, color: colors.indigo },

  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 48, gap: 12 },

  snapshotCard: {
    backgroundColor: colors.surface3, borderRadius: 18, padding: 16, marginBottom: 4,
  },
  snapshotTitle: {
    fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 14,
  },
  snapshotGrid: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  snapshotCell: {
    flex: 1, alignItems: 'center',
    backgroundColor: colors.surface2, borderRadius: 12, padding: 10,
  },
  snapshotVal: { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink, marginBottom: 3 },
  snapshotLabel: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3, textAlign: 'center' },
  snapshotNote: { fontSize: 11, color: colors.ink3, lineHeight: 17 },

  consentBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: 'rgba(52,211,153,0.08)',
    borderWidth: 1, borderColor: 'rgba(52,211,153,0.2)',
    borderRadius: 14, padding: 14, marginBottom: 4,
  },
  consentBannerWithdrawn: {
    backgroundColor: 'rgba(251,191,36,0.08)',
    borderColor: 'rgba(251,191,36,0.2)',
  },
  consentDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.emerald, flexShrink: 0 },
  consentDotWithdrawn: { backgroundColor: colors.amber },
  consentTitle: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  consentSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  consentCheck: { fontSize: 16, color: colors.emerald },

  sectionLabel: {
    fontFamily: fonts.mono, fontSize: 10, color: colors.ink3,
    letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 2, paddingLeft: 4,
  },

  rightCard: {
    backgroundColor: colors.surface3, borderRadius: 18, padding: 14,
  },
  rightCardTop: { flexDirection: 'row', gap: 12, marginBottom: 12, alignItems: 'flex-start' },
  rightIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' },
  rightTitle: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  tagBadge: {
    backgroundColor: 'rgba(99,102,241,0.10)',
    borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2,
  },
  tagText: { fontFamily: fonts.mono, fontSize: 9, color: colors.indigo },
  rightSub: { fontSize: 12, color: colors.ink2, lineHeight: 18 },
  actionBtn: {
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.3)',
    borderRadius: 12, paddingVertical: 10, alignItems: 'center',
    backgroundColor: 'rgba(99,102,241,0.06)',
  },
  actionBtnDanger: {
    borderColor: 'rgba(251,113,133,0.3)',
    backgroundColor: 'rgba(251,113,133,0.06)',
  },
  actionText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.indigo },
  actionTextDanger: { color: colors.rose },

  grievanceCard: {
    backgroundColor: colors.surface3, borderRadius: 18, padding: 16, marginTop: 4,
  },
  grievanceTitle: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 8 },
  grievanceText: { fontSize: 12, color: colors.ink2, lineHeight: 19 },
  grievanceEmail: { color: colors.indigo, fontFamily: fonts.mono },

  // Modals
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  modalCard: {
    backgroundColor: colors.surface2, borderRadius: 24,
    padding: 24, width: '100%', maxWidth: 380,
  },
  modalTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: colors.ink, marginBottom: 10 },
  modalBody: { fontSize: 13, color: colors.ink2, lineHeight: 20, marginBottom: 20 },
  modalBtns: { flexDirection: 'row', gap: 10 },
  modalCancel: {
    flex: 1, borderWidth: 1, borderColor: colors.surface3,
    borderRadius: 14, paddingVertical: 12, alignItems: 'center',
  },
  modalCancelText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink2 },
  modalConfirm: {
    flex: 1, backgroundColor: colors.indigo,
    borderRadius: 14, paddingVertical: 12, alignItems: 'center',
  },
  modalConfirmDanger: { backgroundColor: colors.rose },
  modalConfirmText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#FFFFFF' },
  modalConfirmTextDanger: { color: '#FFFFFF' },

  successOrb: { alignItems: 'center', marginBottom: 16 },
  successGrad: { width: 64, height: 64, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  successBtn: {
    backgroundColor: colors.surface3, borderRadius: 14,
    paddingVertical: 12, alignItems: 'center', marginTop: 4,
  },
  successBtnText: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink },
});
