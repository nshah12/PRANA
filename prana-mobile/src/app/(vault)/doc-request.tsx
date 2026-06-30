import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal,
} from 'react-native';
import { tUi } from '@/i18n';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

const DOC_TYPES = [
  'SALARY_SLIP', 'FORM_16', 'OFFER_LETTER', 'APPOINTMENT_LETTER',
  'RELIEVING_LETTER', 'EXPERIENCE_LETTER', 'INCREMENT_LETTER',
  'PROMOTION_LETTER', 'PF_STATEMENT',
] as const;

type DocRequest = {
  request_id: string;
  doc_type: string;
  employer_name: string;
  doc_period?: string;
  note?: string;
  status: 'PENDING' | 'FULFILLED' | 'REJECTED';
  created_at: string;
};

const STATUS_COLOR: Record<string, string> = {
  PENDING:   colors.amber,
  FULFILLED: colors.emerald,
  REJECTED:  colors.rose,
};

function RequestCard({ req }: { req: DocRequest }) {
  const color = STATUS_COLOR[req.status] ?? colors.ink3;
  return (
    <View style={rc.card}>
      <View style={rc.top}>
        <View style={[rc.typeBadge, { backgroundColor: `${color}15` }]}>
          <Text style={[rc.typeText, { color }]}>{req.doc_type.replace(/_/g, ' ')}</Text>
        </View>
        <View style={[rc.statusBadge, { backgroundColor: `${color}15` }]}>
          <Text style={[rc.statusText, { color }]}>{req.status}</Text>
        </View>
      </View>
      <Text style={rc.employer}>{req.employer_name}</Text>
      {req.doc_period && <Text style={rc.period}>{req.doc_period}</Text>}
      {req.note && <Text style={rc.note}>"{req.note}"</Text>}
      <Text style={rc.date}>{new Date(req.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</Text>
    </View>
  );
}
const rc = StyleSheet.create({
  card:        { backgroundColor: colors.surface3, borderRadius: 16, padding: 14, gap: 6 },
  top:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  typeBadge:   { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, flex: 1, marginRight: 8 },
  typeText:    { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700' },
  statusBadge: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  statusText:  { fontFamily: fonts.mono, fontSize: 9, fontWeight: '700' },
  employer:    { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  period:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  note:        { fontSize: 12, color: colors.ink2, fontStyle: 'italic' },
  date:        { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
});

export default function DocRequestScreen() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [docType, setDocType]   = useState('SALARY_SLIP');
  const [period, setPeriod]     = useState('');
  const [note, setNote]         = useState('');
  const [success, setSuccess]   = useState(false);

  const { data, isLoading, error } = useQuery<{ items: DocRequest[]; total: number }>({
    queryKey: ['doc-requests'],
    queryFn:  () => api.get('/vault/requests').then(r => r.data),
  });

  const { data: profileData } = useQuery<{ employers: { name: string; tenant_id: string }[] }>({
    queryKey: ['vault-profile'],
    queryFn:  () => api.get('/vault/profile').then(r => r.data),
  });

  const [selectedEmployer, setSelectedEmployer] = useState('');
  const employers = profileData?.employers ?? [];

  const submit = useMutation({
    mutationFn: () => api.post('/vault/requests', {
      doc_type:    docType,
      tenant_id:   selectedEmployer || undefined,
      doc_period:  period || undefined,
      note:        note   || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['doc-requests'] });
      setShowForm(false);
      setSuccess(true);
      setPeriod(''); setNote(''); setDocType('SALARY_SLIP');
    },
  });

  const requests = data?.items ?? [];

  return (
    <View style={s.screen}>
      <SafeAreaView edges={['top']} style={s.safe}>
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={s.backBtn}>
            <Text style={s.backText}>‹</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={s.headerTitle}>Document Requests</Text>
            <Text style={s.headerSub}>Ask your employer to upload a missing document</Text>
          </View>
          <Pressable style={s.newBtn} onPress={() => setShowForm(true)}>
            <Text style={s.newBtnText}>＋ New</Text>
          </Pressable>
        </View>
      </SafeAreaView>

      {isLoading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={colors.indigo} />
        </View>
      ) : error ? (
        <View style={s.center}>
          <Text style={s.errorText}>{tUi('REQUESTS_LOAD_FAILED')}</Text>
        </View>
      ) : requests.length === 0 ? (
        <View style={s.center}>
          <Text style={s.emptyIcon}>📩</Text>
          <Text style={s.emptyTitle}>{tUi('NO_REQUESTS_YET')}</Text>
          <Text style={s.emptySub}>Tap "+ New" to ask your employer for a missing document.</Text>
        </View>
      ) : (
        <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>
          <View style={s.summaryRow}>
            {(['PENDING','FULFILLED','REJECTED'] as const).map(st => (
              <View key={st} style={s.summaryCell}>
                <Text style={[s.summaryVal, { color: STATUS_COLOR[st] }]}>
                  {requests.filter(r => r.status === st).length}
                </Text>
                <Text style={s.summaryLabel}>{st}</Text>
              </View>
            ))}
          </View>
          {requests.map(r => <RequestCard key={r.request_id} req={r} />)}
        </ScrollView>
      )}

      {/* New request form modal */}
      <Modal visible={showForm} animationType="slide" transparent onRequestClose={() => setShowForm(false)}>
        <View style={m.overlay}>
          <Pressable style={m.backdrop} onPress={() => setShowForm(false)} />
          <View style={m.panel}>
            <View style={m.handle} />
            <Text style={m.title}>Request a document</Text>

            <Text style={m.label}>Document type</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {DOC_TYPES.map(dt => (
                  <Pressable
                    key={dt}
                    style={[m.chip, docType === dt && m.chipActive]}
                    onPress={() => setDocType(dt)}
                  >
                    <Text style={[m.chipText, docType === dt && m.chipTextActive]}>
                      {dt.replace(/_/g, ' ')}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </ScrollView>

            {employers.length > 0 && (
              <>
                <Text style={m.label}>Employer (optional)</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    {employers.map(e => (
                      <Pressable
                        key={e.tenant_id}
                        style={[m.chip, selectedEmployer === e.tenant_id && m.chipActive]}
                        onPress={() => setSelectedEmployer(e.tenant_id)}
                      >
                        <Text style={[m.chipText, selectedEmployer === e.tenant_id && m.chipTextActive]}>
                          {e.name}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                </ScrollView>
              </>
            )}

            <Text style={m.label}>Period (optional, e.g. 2024-03)</Text>
            <TextInput
              style={m.input}
              value={period}
              onChangeText={setPeriod}
              placeholder="YYYY-MM"
              placeholderTextColor={colors.ink3}
              keyboardType="numbers-and-punctuation"
            />

            <Text style={m.label}>Note (optional)</Text>
            <TextInput
              style={[m.input, m.textarea]}
              value={note}
              onChangeText={setNote}
              placeholder="Any context for your employer…"
              placeholderTextColor={colors.ink3}
              multiline
              numberOfLines={3}
            />

            <Pressable
              style={[m.submitBtn, submit.isPending && { opacity: 0.6 }]}
              onPress={() => submit.mutate()}
              disabled={submit.isPending}
            >
              {submit.isPending
                ? <ActivityIndicator size="small" color="#FFF" />
                : <Text style={m.submitText}>Send request</Text>
              }
            </Pressable>
          </View>
        </View>
      </Modal>

      {/* Success modal */}
      <Modal visible={success} animationType="fade" transparent onRequestClose={() => setSuccess(false)}>
        <View style={m.overlay}>
          <View style={m.successCard}>
            <Text style={{ fontSize: 40, marginBottom: 12 }}>✓</Text>
            <Text style={m.title}>Request sent</Text>
            <Text style={m.successSub}>Your employer has been notified. Requests are typically fulfilled within 3 business days.</Text>
            <Pressable style={m.submitBtn} onPress={() => setSuccess(false)}>
              <Text style={m.submitText}>Done</Text>
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
  newBtn:       { backgroundColor: 'rgba(99,102,241,0.12)', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 },
  newBtnText:   { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo },
  center:       { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10, padding: 32 },
  errorText:    { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.rose, textAlign: 'center' },
  emptyIcon:    { fontSize: 40 },
  emptyTitle:   { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink },
  emptySub:     { fontSize: 13, color: colors.ink3, textAlign: 'center', lineHeight: 20 },
  body:         { flex: 1 },
  bodyContent:  { padding: 16, paddingBottom: 60, gap: 10 },
  summaryRow:   { flexDirection: 'row', backgroundColor: colors.surface3, borderRadius: 16, padding: 16, marginBottom: 4 },
  summaryCell:  { flex: 1, alignItems: 'center' },
  summaryVal:   { fontFamily: fonts.displayBold, fontSize: 22 },
  summaryLabel: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
});

const m = StyleSheet.create({
  overlay:    { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  backdrop:   { flex: 1 },
  panel:      { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 22, paddingBottom: 40 },
  handle:     { width: 36, height: 4, backgroundColor: colors.surface3, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  title:      { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, marginBottom: 18 },
  label:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, letterSpacing: 0.8, marginBottom: 8 },
  chip:       { borderWidth: 1, borderColor: colors.surface3, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7 },
  chipActive: { backgroundColor: colors.indigo, borderColor: colors.indigo },
  chipText:   { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.ink2 },
  chipTextActive: { color: '#FFF' },
  input:      { backgroundColor: colors.surface3, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: colors.ink, marginBottom: 14 },
  textarea:   { height: 80, textAlignVertical: 'top' },
  submitBtn:  { backgroundColor: colors.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center', marginTop: 4 },
  submitText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#FFF' },
  successCard:{ backgroundColor: colors.surface, borderRadius: 24, margin: 32, padding: 28, alignItems: 'center', gap: 8 },
  successSub: { fontSize: 13, color: colors.ink2, textAlign: 'center', lineHeight: 20, marginBottom: 8 },
});
