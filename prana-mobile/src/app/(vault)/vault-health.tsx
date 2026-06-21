import React from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { colors, fonts } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

type HealthData = {
  overall_score: number;
  gap_count: number;
  gap_detail: { doc_type: string; employer: string; severity: string }[];
};

type ProfileData = { employers: { name: string; dol?: string }[] };
type DocsData   = { documents: { doc_type: string; doc_period?: string; tenant_id?: string }[]; total: number };

const SEV_COLOR: Record<string, string> = {
  HIGH:   '#EF4444',
  MEDIUM: '#F59E0B',
  LOW:    '#6366F1',
};

function ScoreRing({ score }: { score: number }) {
  const color = score >= 80 ? colors.emerald : score >= 50 ? colors.amber : colors.rose;
  return (
    <View style={ring.wrap}>
      <View style={[ring.circle, { borderColor: color }]}>
        <Text style={[ring.score, { color }]}>{score}</Text>
        <Text style={ring.label}>/ 100</Text>
      </View>
      <Text style={ring.sub}>Vault Health Score</Text>
    </View>
  );
}
const ring = StyleSheet.create({
  wrap:   { alignItems: 'center', paddingVertical: 24 },
  circle: { width: 120, height: 120, borderRadius: 60, borderWidth: 6, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  score:  { fontFamily: fonts.displayBold, fontSize: 36, lineHeight: 40 },
  label:  { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3 },
  sub:    { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3, letterSpacing: 0.8 },
});

function BreakdownRow({ label, status }: { label: string; status: 'ok' | 'warn' | 'bad' }) {
  const icon  = status === 'ok' ? '✓' : status === 'warn' ? '⚠' : '✕';
  const color = status === 'ok' ? colors.emerald : status === 'warn' ? colors.amber : colors.rose;
  return (
    <View style={br.row}>
      <View style={[br.icon, { backgroundColor: `${color}20` }]}>
        <Text style={[br.iconText, { color }]}>{icon}</Text>
      </View>
      <Text style={br.label}>{label}</Text>
    </View>
  );
}
const br = StyleSheet.create({
  row:      { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9 },
  icon:     { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  iconText: { fontSize: 13, fontWeight: '700' },
  label:    { fontSize: 13, color: colors.ink2, flex: 1 },
});

export default function VaultHealthScreen() {
  const { data: health, isLoading: loadingH, error: errH } = useQuery<HealthData>({
    queryKey: ['vault-health'],
    queryFn:  () => api.get('/vault/health').then(r => r.data),
  });

  const { data: profile } = useQuery<ProfileData>({
    queryKey: ['vault-profile'],
    queryFn:  () => api.get('/vault/profile').then(r => r.data),
  });

  const { data: docsData } = useQuery<DocsData>({
    queryKey: ['vault-docs-health'],
    queryFn:  () => api.get('/vault/documents', { params: { limit: 200 } }).then(r => r.data),
  });

  const score    = health?.overall_score ?? 0;
  const gaps     = health?.gap_detail    ?? [];
  const docs     = docsData?.documents   ?? [];
  const employers= profile?.employers    ?? [];

  const hasProof    = docs.some(d => ['APPOINTMENT_LETTER','OFFER_LETTER'].includes(d.doc_type));
  const recentSlips = docs.filter(d => {
    if (d.doc_type !== 'SALARY_SLIP') return false;
    const p = d.doc_period;
    if (!p) return false;
    const [y, m] = p.split('-').map(Number);
    const cutoff = new Date(); cutoff.setMonth(cutoff.getMonth() - 12);
    return new Date(y, (m || 1) - 1) >= cutoff;
  });
  const form16s     = docs.filter(d => d.doc_type === 'FORM_16');
  const alumniMissing = employers
    .filter((e: any) => e.dol)
    .some((e: any) => !docs.some(d => d.tenant_id === (e.tenant_id ?? e.id) && d.doc_type === 'SALARY_SLIP'));

  const breakdown: { label: string; status: 'ok' | 'warn' | 'bad' }[] = [
    { label: 'Employment proof (offer / appointment)', status: hasProof ? 'ok' : 'bad' },
    { label: 'Salary slips — last 12 months',          status: recentSlips.length >= 6 ? 'ok' : recentSlips.length > 0 ? 'warn' : 'bad' },
    { label: 'Form 16 history',                        status: form16s.length >= Math.max(1, employers.length) ? 'ok' : form16s.length > 0 ? 'warn' : 'bad' },
    { label: 'Historic slips from previous employers', status: alumniMissing ? 'bad' : 'ok' },
  ];

  const computedScore = score > 0
    ? score
    : Math.round(breakdown.filter(r => r.status === 'ok').length / breakdown.length * 100);

  return (
    <View style={s.screen}>
      <SafeAreaView edges={['top']} style={s.safe}>
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={s.backBtn}>
            <Text style={s.backText}>‹</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={s.headerTitle}>Vault Health</Text>
            <Text style={s.headerSub}>Document completeness across all employers</Text>
          </View>
        </View>
      </SafeAreaView>

      {loadingH ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={colors.indigo} />
          <Text style={s.centerText}>Checking your vault…</Text>
        </View>
      ) : errH ? (
        <View style={s.center}>
          <Text style={s.errorText}>Could not load health data. Try again later.</Text>
        </View>
      ) : (
        <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>

          {/* Score ring */}
          <View style={s.card}>
            <ScoreRing score={computedScore} />
            <View style={s.statsRow}>
              <View style={s.stat}>
                <Text style={s.statVal}>{docs.length}</Text>
                <Text style={s.statLabel}>Documents</Text>
              </View>
              <View style={s.statDiv} />
              <View style={s.stat}>
                <Text style={s.statVal}>{employers.length}</Text>
                <Text style={s.statLabel}>Employers</Text>
              </View>
              <View style={s.statDiv} />
              <View style={s.stat}>
                <Text style={[s.statVal, gaps.length > 0 && { color: colors.rose }]}>{gaps.length}</Text>
                <Text style={s.statLabel}>Gaps</Text>
              </View>
            </View>
          </View>

          {/* Breakdown */}
          <Text style={s.sectionLabel}>COMPLETENESS BREAKDOWN</Text>
          <View style={s.card}>
            {breakdown.map(r => <BreakdownRow key={r.label} label={r.label} status={r.status} />)}
          </View>

          {/* Gaps */}
          {gaps.length > 0 && (
            <>
              <Text style={s.sectionLabel}>GAPS TO FILL</Text>
              {gaps.map((g, i) => (
                <View key={i} style={s.gapCard}>
                  <View style={s.gapLeft}>
                    <View style={[s.sevDot, { backgroundColor: SEV_COLOR[g.severity] ?? colors.ink3 }]} />
                    <View>
                      <Text style={s.gapType}>{g.doc_type.replace(/_/g, ' ')}</Text>
                      <Text style={s.gapEmp}>{g.employer}</Text>
                    </View>
                  </View>
                  <View style={[s.sevBadge, { backgroundColor: `${SEV_COLOR[g.severity] ?? colors.ink3}18` }]}>
                    <Text style={[s.sevText, { color: SEV_COLOR[g.severity] ?? colors.ink3 }]}>{g.severity}</Text>
                  </View>
                </View>
              ))}
            </>
          )}

          {/* Empty gaps */}
          {gaps.length === 0 && computedScore >= 80 && (
            <View style={s.allGoodCard}>
              <Text style={s.allGoodIcon}>✓</Text>
              <Text style={s.allGoodTitle}>Vault looks complete</Text>
              <Text style={s.allGoodSub}>No critical gaps detected across your employers.</Text>
            </View>
          )}

          {/* Doc request CTA */}
          <Pressable style={s.ctaCard} onPress={() => router.push('/(vault)/doc-request' as any)}>
            <Text style={s.ctaIcon}>📩</Text>
            <View style={{ flex: 1 }}>
              <Text style={s.ctaTitle}>Request missing documents</Text>
              <Text style={s.ctaSub}>Ask your employer to upload a specific document</Text>
            </View>
            <Text style={s.ctaArrow}>›</Text>
          </Pressable>

        </ScrollView>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  screen:      { flex: 1, backgroundColor: colors.surface },
  safe:        { backgroundColor: colors.surface },
  header:      { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  backBtn:     { padding: 4, marginRight: 2 },
  backText:    { fontSize: 28, color: colors.ink2, lineHeight: 32 },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: colors.ink },
  headerSub:   { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  center:      { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  centerText:  { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.ink3 },
  errorText:   { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.rose, textAlign: 'center' },
  body:        { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 60, gap: 10 },
  sectionLabel:{ fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, letterSpacing: 1.2, textTransform: 'uppercase', paddingLeft: 4, marginTop: 4 },
  card:        { backgroundColor: colors.surface3, borderRadius: 18, padding: 16 },
  statsRow:    { flexDirection: 'row', alignItems: 'center', paddingTop: 4 },
  stat:        { flex: 1, alignItems: 'center' },
  statVal:     { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink },
  statLabel:   { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  statDiv:     { width: 1, height: 32, backgroundColor: colors.surface },
  gapCard:     { backgroundColor: colors.surface3, borderRadius: 14, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  gapLeft:     { flexDirection: 'row', alignItems: 'center', gap: 10 },
  sevDot:      { width: 8, height: 8, borderRadius: 4 },
  gapType:     { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  gapEmp:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  sevBadge:    { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  sevText:     { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700' },
  allGoodCard: { backgroundColor: 'rgba(52,211,153,0.08)', borderWidth: 1, borderColor: 'rgba(52,211,153,0.2)', borderRadius: 18, padding: 24, alignItems: 'center', gap: 8 },
  allGoodIcon: { fontSize: 28, color: colors.emerald },
  allGoodTitle:{ fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink },
  allGoodSub:  { fontSize: 12, color: colors.ink3, textAlign: 'center' },
  ctaCard:     { backgroundColor: colors.surface3, borderRadius: 18, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 12 },
  ctaIcon:     { fontSize: 22 },
  ctaTitle:    { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  ctaSub:      { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  ctaArrow:    { fontSize: 22, color: colors.ink3 },
});
