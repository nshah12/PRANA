import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Modal, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

type AccessEvent = {
  access_id: string;
  actor_type: string;
  actor_id: string;
  access_type: string;
  access_channel: string;
  ip_city?: string;
  accessed_at: string;
  watermark_applied: boolean;
  is_flagged: boolean;
};

type ExtractionLog = {
  document_id: string;
  doc_type: string;
  processed_at: string;
  pan_destroyed_ms?: number;
  output_type: string;
};

const ACTOR_ICON: Record<string, string> = {
  EMPLOYEE: '👤',
  OA_USER:  '🏢',
  SYSTEM:   '🤖',
  SHARE:    '↗',
};

function AccessRow({ ev }: { ev: AccessEvent }) {
  return (
    <View style={ar.row}>
      <View style={ar.iconWrap}>
        <Text style={ar.icon}>{ACTOR_ICON[ev.actor_type] ?? '?'}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <View style={ar.top}>
          <Text style={ar.type}>{ev.access_type}</Text>
          {ev.is_flagged && <View style={ar.flagBadge}><Text style={ar.flagText}>FLAGGED</Text></View>}
          {ev.watermark_applied && <Text style={ar.wm}>🔏</Text>}
        </View>
        <Text style={ar.channel}>{ev.access_channel} · {ev.ip_city ?? 'Location private'}</Text>
        <Text style={ar.date}>{new Date(ev.accessed_at).toLocaleString('en-IN', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })}</Text>
      </View>
    </View>
  );
}
const ar = StyleSheet.create({
  row:       { flexDirection: 'row', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  iconWrap:  { width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(99,102,241,0.10)', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  icon:      { fontSize: 15 },
  top:       { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 },
  type:      { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  flagBadge: { backgroundColor: 'rgba(251,113,133,0.15)', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  flagText:  { fontFamily: fonts.mono, fontSize: 9, color: colors.rose, fontWeight: '700' },
  wm:        { fontSize: 12 },
  channel:   { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  date:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 1 },
});

export default function PrivacyScreen() {
  const queryClient = useQueryClient();
  const [showGrievance, setShowGrievance] = useState(false);
  const [grievanceText, setGrievanceText] = useState('');
  const [grievanceSent, setGrievanceSent] = useState(false);

  const { data: accessData, isLoading: loadingAccess } = useQuery<{ items: AccessEvent[]; total: number }>({
    queryKey: ['privacy-access-log'],
    queryFn:  () => api.get('/vault/access-log', { params: { limit: 20 } }).then(r => r.data),
  });

  const { data: extractData } = useQuery<{ items: ExtractionLog[] }>({
    queryKey: ['privacy-extraction-log'],
    queryFn:  () => api.get('/vault/extraction-log', { params: { limit: 10 } }).then(r => r.data),
  });

  const grievanceMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/grievance', { description: grievanceText }),
    onSuccess:  () => { setShowGrievance(false); setGrievanceSent(true); setGrievanceText(''); },
  });

  const exportMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/export'),
  });

  const accessEvents  = accessData?.items  ?? [];
  const extractEvents = extractData?.items  ?? [];
  const flaggedCount  = accessEvents.filter(e => e.is_flagged).length;

  return (
    <View style={s.screen}>
      <SafeAreaView edges={['top']} style={s.safe}>
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={s.backBtn}>
            <Text style={s.backText}>‹</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={s.headerTitle}>Privacy Cockpit</Text>
            <Text style={s.headerSub}>See exactly who accessed your data and when</Text>
          </View>
        </View>
      </SafeAreaView>

      <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>

        {/* Summary stats */}
        <View style={s.statsCard}>
          <View style={s.stat}>
            <Text style={s.statVal}>{accessData?.total ?? 0}</Text>
            <Text style={s.statLabel}>Total accesses</Text>
          </View>
          <View style={s.statDiv} />
          <View style={s.stat}>
            <Text style={[s.statVal, flaggedCount > 0 && { color: colors.rose }]}>{flaggedCount}</Text>
            <Text style={s.statLabel}>Flagged</Text>
          </View>
          <View style={s.statDiv} />
          <View style={s.stat}>
            <Text style={s.statVal}>{extractEvents.length}</Text>
            <Text style={s.statLabel}>AI processed</Text>
          </View>
        </View>

        {/* AI processing transparency */}
        {extractEvents.length > 0 && (
          <>
            <Text style={s.sectionLabel}>AI PROCESSING LOG</Text>
            <View style={s.card}>
              {extractEvents.map((ev, i) => (
                <View key={ev.document_id} style={[s.extractRow, i < extractEvents.length - 1 && { borderBottomWidth: 1, borderBottomColor: colors.surface3 }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.extractType}>{ev.doc_type.replace(/_/g, ' ')}</Text>
                    <Text style={s.extractDetail}>
                      {ev.pan_destroyed_ms != null ? `PAN destroyed in ${ev.pan_destroyed_ms}ms · ` : ''}
                      Output: {ev.output_type}
                    </Text>
                    <Text style={s.extractDate}>
                      {new Date(ev.processed_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}
                    </Text>
                  </View>
                  <View style={s.rawBadge}>
                    <Text style={s.rawText}>No ₹ stored</Text>
                  </View>
                </View>
              ))}
              <Text style={s.privacyNote}>
                Raw salary figures are processed in-memory and immediately discarded. Only growth indices and consistency verdicts are retained.
              </Text>
            </View>
          </>
        )}

        {/* Access log */}
        <Text style={s.sectionLabel}>WHO ACCESSED YOUR VAULT</Text>
        {loadingAccess ? (
          <View style={s.center}><ActivityIndicator color={colors.indigo} /></View>
        ) : accessEvents.length === 0 ? (
          <View style={s.card}>
            <Text style={s.emptyText}>No access events recorded yet.</Text>
          </View>
        ) : (
          <View style={s.card}>
            {accessEvents.map(ev => <AccessRow key={ev.access_id} ev={ev} />)}
          </View>
        )}

        {/* Actions */}
        <Text style={s.sectionLabel}>ACTIONS</Text>

        <Pressable
          style={s.actionCard}
          onPress={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
        >
          <Text style={s.actionIcon}>📥</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Export privacy report</Text>
            <Text style={s.actionSub}>Download your full access log and processing history</Text>
          </View>
          {exportMutation.isPending
            ? <ActivityIndicator size="small" color={colors.indigo} />
            : <Text style={s.actionArrow}>›</Text>
          }
        </Pressable>

        {exportMutation.isSuccess && (
          <View style={s.successBanner}>
            <Text style={s.successText}>✓ Export requested — link will be sent to your mobile number within 24 hours.</Text>
          </View>
        )}

        <Pressable style={s.actionCard} onPress={() => setShowGrievance(true)}>
          <Text style={s.actionIcon}>📋</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>File a privacy grievance</Text>
            <Text style={s.actionSub}>Raise a concern about unauthorised access or data misuse</Text>
          </View>
          <Text style={s.actionArrow}>›</Text>
        </Pressable>

        {grievanceSent && (
          <View style={s.successBanner}>
            <Text style={s.successText}>✓ Grievance filed — our DPDP officer will respond within 7 business days.</Text>
          </View>
        )}

      </ScrollView>

      {/* Grievance form */}
      <Modal visible={showGrievance} animationType="slide" transparent onRequestClose={() => setShowGrievance(false)}>
        <View style={gm.overlay}>
          <Pressable style={gm.backdrop} onPress={() => setShowGrievance(false)} />
          <View style={gm.panel}>
            <View style={gm.handle} />
            <Text style={gm.title}>File a Privacy Grievance</Text>
            <Text style={gm.sub}>
              For unresolved data concerns. Our DPDP Grievance Officer will respond within 7 business days.
            </Text>
            <Text style={gm.label}>Describe your concern</Text>
            <TextInput
              style={gm.input}
              value={grievanceText}
              onChangeText={setGrievanceText}
              placeholder="What happened? Which document or access event concerns you?"
              placeholderTextColor={colors.ink3}
              multiline
              numberOfLines={5}
              textAlignVertical="top"
            />
            <Pressable
              style={[gm.submitBtn, (grievanceMutation.isPending || grievanceText.trim().length < 10) && { opacity: 0.5 }]}
              onPress={() => grievanceMutation.mutate()}
              disabled={grievanceMutation.isPending || grievanceText.trim().length < 10}
            >
              {grievanceMutation.isPending
                ? <ActivityIndicator size="small" color="#FFF" />
                : <Text style={gm.submitText}>Submit grievance</Text>
              }
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  screen:       { flex: 1, backgroundColor: colors.surface },
  safe:         { backgroundColor: colors.surface },
  header:       { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  backBtn:      { padding: 4, marginRight: 2 },
  backText:     { fontSize: 28, color: colors.ink2, lineHeight: 32 },
  headerTitle:  { fontFamily: fonts.displayBold, fontSize: 17, color: colors.ink },
  headerSub:    { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  body:         { flex: 1 },
  bodyContent:  { padding: 16, paddingBottom: 60, gap: 10 },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, letterSpacing: 1.2, textTransform: 'uppercase', paddingLeft: 4, marginTop: 4 },
  statsCard:    { flexDirection: 'row', backgroundColor: colors.surface3, borderRadius: 18, padding: 16, alignItems: 'center' },
  stat:         { flex: 1, alignItems: 'center' },
  statVal:      { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink },
  statLabel:    { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  statDiv:      { width: 1, height: 32, backgroundColor: colors.surface },
  card:         { backgroundColor: colors.surface3, borderRadius: 18, padding: 16 },
  extractRow:   { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 10 },
  extractType:  { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  extractDetail:{ fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  extractDate:  { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 1 },
  rawBadge:     { backgroundColor: 'rgba(52,211,153,0.12)', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  rawText:      { fontFamily: fonts.mono, fontSize: 9, color: colors.emerald, fontWeight: '700' },
  privacyNote:  { fontSize: 11, color: colors.ink3, lineHeight: 17, marginTop: 12 },
  center:       { padding: 24, alignItems: 'center' },
  emptyText:    { fontSize: 13, color: colors.ink3, textAlign: 'center' },
  actionCard:   { backgroundColor: colors.surface3, borderRadius: 18, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 12 },
  actionIcon:   { fontSize: 22 },
  actionTitle:  { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  actionSub:    { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  actionArrow:  { fontSize: 22, color: colors.ink3 },
  successBanner:{ backgroundColor: 'rgba(52,211,153,0.10)', borderRadius: 12, padding: 12 },
  successText:  { fontSize: 12, color: colors.emerald, lineHeight: 18 },
});

const gm = StyleSheet.create({
  overlay:    { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  backdrop:   { flex: 1 },
  panel:      { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 22, paddingBottom: 40 },
  handle:     { width: 36, height: 4, backgroundColor: colors.surface3, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  title:      { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, marginBottom: 8 },
  sub:        { fontSize: 13, color: colors.ink2, lineHeight: 20, marginBottom: 18 },
  label:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, letterSpacing: 0.8, marginBottom: 8 },
  input:      { backgroundColor: colors.surface3, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: colors.ink, height: 120, marginBottom: 16 },
  submitBtn:  { backgroundColor: colors.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center' },
  submitText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#FFF' },
});
