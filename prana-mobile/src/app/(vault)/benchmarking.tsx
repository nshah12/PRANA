import React from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts, radius } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

type BenchmarkItem = {
  cohort_key:      string;
  designation:     string;
  city:            string;
  experience_band: string;
  percentile_band: string | null;
  label_text:      string;
  suppressed:      boolean;
  cohort_progress: { current: number; needed: number } | null;
  data_freshness:  string;
  computed_at:     string;
};

// Parse cohort_key → "Senior Engineer · FinTech · Bengaluru · 5–8y"
function formatCohortKey(key: string): string {
  return key.split('|').map(s =>
    s.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  ).join(' · ');
}

// Percentile band → accent color
function bandColor(band: string | null): string {
  if (!band) return '#64748B';
  if (band.startsWith('P75')) return '#7C3AED';
  if (band.startsWith('P60')) return '#0EA5E9';
  if (band.startsWith('P40')) return '#10B981';
  return '#F59E0B';
}

export default function BenchmarkingScreen() {
  const qc = useQueryClient();

  const { data: consentData, isLoading: consentLoading } = useQuery({
    queryKey: ['benchmark-consent'],
    queryFn: () => api.get('/v1/benchmarking/consent').then(r => r.data),
  });

  const { data: positionData, isLoading: positionLoading } = useQuery({
    queryKey: ['benchmark-position'],
    queryFn: () => api.get('/v1/benchmarking/my-position').then(r => r.data),
    enabled: consentData?.peer_benchmark_consent === true,
  });

  const consentMutation = useMutation({
    mutationFn: (grant: boolean) =>
      api.post('/v1/benchmarking/consent', { grant }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['benchmark-consent'] });
      qc.invalidateQueries({ queryKey: ['benchmark-position'] });
    },
  });

  const opted = consentData?.peer_benchmark_consent ?? false;
  const items: BenchmarkItem[] = positionData?.items ?? [];

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹</Text>
        </Pressable>
        <Text style={styles.title}>Comp Benchmarking</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Consent card */}
        <View style={styles.consentCard}>
          <View style={{ flex: 1, marginRight: 12 }}>
            <Text style={styles.consentTitle}>Contribute anonymously</Text>
            <Text style={styles.consentSub}>
              Your compensation data helps build industry benchmarks.
              All data is k-anonymous — your individual figures are never shared.
            </Text>
          </View>
          {consentLoading
            ? <ActivityIndicator size="small" color={colors.emerald ?? '#10B981'} />
            : <Switch
                value={opted}
                onValueChange={v => consentMutation.mutate(v)}
                trackColor={{ true: colors.emerald ?? '#10B981', false: '#CBD5E1' }}
                thumbColor="#FFFFFF"
                disabled={consentMutation.isPending}
              />
          }
        </View>

        {/* Privacy note when opted in */}
        {opted && (
          <View style={styles.privacyNote}>
            <Text style={styles.privacyNoteText}>
              ✓ You're contributing. Your specific figures are never visible to anyone — only aggregated bands with 50+ contributors are published.
            </Text>
          </View>
        )}

        {/* Position cards */}
        {opted && (
          <>
            <Text style={styles.sectionLabel}>YOUR MARKET POSITION</Text>

            {positionLoading && (
              <View style={styles.loadingBox}>
                <ActivityIndicator size="large" color={colors.sky ?? '#0EA5E9'} />
                <Text style={styles.loadingText}>Computing your position…</Text>
              </View>
            )}

            {!positionLoading && items.length === 0 && (
              <View style={styles.emptyBox}>
                <Text style={styles.emptyIcon}>📊</Text>
                <Text style={styles.emptyTitle}>Building your benchmark</Text>
                <Text style={styles.emptySub}>
                  Your percentile will appear once your cohort has enough contributors.
                  Check back after your next salary cycle.
                </Text>
              </View>
            )}

            {items.map(item => (
              <View key={item.cohort_key} style={styles.positionCard}>
                <Text style={styles.cohortLabel}>{formatCohortKey(item.cohort_key)}</Text>

                {item.suppressed ? (
                  <View>
                    <View style={styles.suppressedRow}>
                      <Text style={styles.suppressedIcon}>🔒</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.suppressedTitle}>Building your benchmark</Text>
                        <Text style={styles.suppressedSub}>{item.label_text}</Text>
                      </View>
                    </View>
                    {item.cohort_progress && (
                      <View style={styles.progressBar}>
                        <View style={[styles.progressFill, {
                          width: `${Math.min((item.cohort_progress.current / item.cohort_progress.needed) * 100, 100)}%` as any,
                        }]} />
                      </View>
                    )}
                  </View>
                ) : (
                  <>
                    <View style={[styles.bandPill, { backgroundColor: bandColor(item.percentile_band) + '22' }]}>
                      <Text style={[styles.bandText, { color: bandColor(item.percentile_band) }]}>
                        {item.percentile_band}
                      </Text>
                    </View>
                    <Text style={styles.labelText}>{item.label_text}</Text>
                    <Text style={styles.cohortSize}>Updated {item.data_freshness}</Text>
                  </>
                )}
              </View>
            ))}
          </>
        )}

        {/* Opted-out state */}
        {!opted && !consentLoading && (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyIcon}>🏦</Text>
            <Text style={styles.emptyTitle}>See where you stand</Text>
            <Text style={styles.emptySub}>
              Enable contribution above to unlock your market percentile.
              Your data is always anonymised — no one can see your individual figures.
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: '#F8FAFC' },
  header:  { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, gap: 8, borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  back:    { padding: 4 },
  backText:{ fontSize: 24, color: '#475569', lineHeight: 28 },
  title:   { fontSize: 17, fontFamily: fonts.displayBold, color: '#0F172A' },

  content: { padding: 16, paddingBottom: 40, gap: 16 },

  consentCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16,
    padding: 16, flexDirection: 'row', alignItems: 'center',
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, elevation: 2,
  },
  consentTitle: { fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#0F172A', marginBottom: 4 },
  consentSub:   { fontSize: 12, color: '#64748B', lineHeight: 17 },

  privacyNote: { backgroundColor: '#F0FDF4', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#BBF7D0' },
  privacyNoteText: { fontSize: 12, color: '#166534', lineHeight: 17 },

  sectionLabel: { fontSize: 11, fontFamily: fonts.mono, color: '#94A3B8', letterSpacing: 1 },

  loadingBox: { alignItems: 'center', paddingVertical: 40, gap: 12 },
  loadingText: { fontSize: 13, color: '#94A3B8' },

  emptyBox:  { alignItems: 'center', paddingVertical: 40, paddingHorizontal: 24 },
  emptyIcon: { fontSize: 36, marginBottom: 12 },
  emptyTitle:{ fontSize: 15, fontFamily: fonts.bodySemiBold, color: '#334155', marginBottom: 6 },
  emptySub:  { fontSize: 13, color: '#64748B', textAlign: 'center', lineHeight: 19 },

  positionCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, elevation: 2,
    gap: 8,
  },
  cohortLabel: { fontSize: 12, color: '#64748B', fontFamily: fonts.mono },
  bandPill:    { alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 4, borderRadius: 20 },
  bandText:    { fontSize: 13, fontFamily: fonts.bodySemiBold },
  labelText:   { fontSize: 14, color: '#1E293B', lineHeight: 20 },
  cohortSize:  { fontSize: 11, color: '#94A3B8' },

  suppressedRow:  { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  suppressedIcon: { fontSize: 20 },
  suppressedTitle:{ fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#475569', marginBottom: 2 },
  suppressedSub:  { fontSize: 12, color: '#94A3B8', lineHeight: 17 },
  progressBar:    { height: 5, backgroundColor: '#E2E8F0', borderRadius: 3, marginTop: 10, overflow: 'hidden' },
  progressFill:   { height: 5, backgroundColor: '#0EA5E9', borderRadius: 3 },
});
