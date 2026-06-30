import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, Dimensions, ActivityIndicator } from 'react-native';
import { tUi } from '@/i18n';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts, gradJourney, gradTopBg } from '@/prana-theme/tokens';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';

const SCREEN_W = Dimensions.get('window').width;
const CHART_H = 160;
const BAR_W = 36;
const BAR_GAP = 16;
const CHART_LEFT_PAD = 38;

type ChartMode = 'P' | 'A';

interface GrowthPoint {
  period: string;
  index: number;
  employer_id: string;
  employer_name: string;
  doc_type: string;
  note: string;
}

interface Employer {
  id: string;
  name: string;
  role: string;
  from: string | null;
  to: string | null;
}

interface CareerEvent {
  id: string;
  type: string;
  label: string;
  employer_id: string;
  at: string | null;
}

interface CareerData {
  growth_data: GrowthPoint[];
  employers: Employer[];
  events: CareerEvent[];
}

// Palette for up to 6 employers — cycles if more
const EMPLOYER_PALETTE: [string, string][] = [
  ['#34D399', '#059669'],
  ['#818CF8', '#6366F1'],
  ['#FB923C', '#EA580C'],
  ['#F472B6', '#DB2777'],
  ['#38BDF8', '#0284C7'],
  ['#A3E635', '#65A30D'],
];
const EMPLOYER_TINT = EMPLOYER_PALETTE.map(([a]) => a);

function employerColorIndex(employers: Employer[], employer_id: string): number {
  const idx = employers.findIndex(e => e.id === employer_id);
  return idx >= 0 ? idx % EMPLOYER_PALETTE.length : 0;
}

// ── Growth chart ──────────────────────────────────────────────────────────────
function GrowthChart({ data, employers, mode }: { data: GrowthPoint[]; employers: Employer[]; mode: ChartMode }) {
  const [activeIdx, setActiveIdx] = useState(data.length - 1);
  if (!data.length) return null;
  const active = data[activeIdx] ?? data[0];
  const colorIdx = employerColorIndex(employers, active.employer_id);
  const tint = EMPLOYER_TINT[colorIdx];
  const gradient = EMPLOYER_PALETTE[colorIdx];

  const maxVal = Math.max(...data.map(d => d.index), 1);
  const chartContentW = CHART_LEFT_PAD + data.length * (BAR_W + BAR_GAP) + BAR_GAP;

  const growthVsBaseline = active.index - 100;
  const prev = activeIdx > 0 ? data[activeIdx - 1].index : active.index;
  const growthVsPrev = active.index - prev;

  return (
    <View style={chart.wrap}>
      <View style={chart.tooltip}>
        <View style={[chart.tooltipDot, { backgroundColor: tint }]} />
        <View style={{ flex: 1 }}>
          <Text style={chart.tooltipIndex}>
            {active.index}<Text style={chart.tooltipIndexUnit}> idx</Text>
          </Text>
          <Text style={chart.tooltipMeta}>{active.period}  ·  {active.employer_name}</Text>
        </View>
        <View style={chart.tooltipBadges}>
          <View style={[chart.badge, { backgroundColor: 'rgba(52,211,153,0.12)' }]}>
            <Text style={[chart.badgeText, { color: '#059669' }]}>+{growthVsBaseline}% since start</Text>
          </View>
          {growthVsPrev > 0 && (
            <View style={[chart.badge, { backgroundColor: 'rgba(99,102,241,0.10)', marginTop: 3 }]}>
              <Text style={[chart.badgeText, { color: colors.indigo }]}>+{growthVsPrev}pts this step</Text>
            </View>
          )}
        </View>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={chart.scroll}
        contentContainerStyle={{ width: Math.max(chartContentW, SCREEN_W - 32) }}
      >
        <View style={[chart.barsArea, { height: CHART_H }]}>
          {[25, 50, 75, 100].map(pct => {
            const y = (pct / 100) * CHART_H;
            const val = Math.round(maxVal * (pct / 100));
            return (
              <View key={pct} style={[chart.guideLine, { bottom: y }]}>
                <Text style={chart.guideLabel} numberOfLines={1}>{val}</Text>
                <View style={chart.guideRule} />
              </View>
            );
          })}
          <View style={[chart.bars, { paddingLeft: CHART_LEFT_PAD }]}>
            {data.map((d, i) => {
              const h = (d.index / maxVal) * CHART_H;
              const isActive = i === activeIdx;
              const ci = employerColorIndex(employers, d.employer_id);
              const isSwitch = i > 0 && d.employer_id !== data[i - 1].employer_id;
              return (
                <Pressable key={`${d.period}-${i}`} onPress={() => setActiveIdx(i)} style={[chart.barWrap, { width: BAR_W + BAR_GAP }]}>
                  {isSwitch && <View style={chart.switchLine} />}
                  <View style={[chart.barTrack, { height: CHART_H }]}>
                    {isActive ? (
                      <LinearGradient
                        colors={EMPLOYER_PALETTE[ci]}
                        start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }}
                        style={[chart.bar, { height: h, width: BAR_W }]}
                      />
                    ) : (
                      <View style={[chart.barInactive, { height: h, width: BAR_W, backgroundColor: EMPLOYER_TINT[ci] + '33' }]} />
                    )}
                  </View>
                  <Text style={[chart.barLabel, isActive && chart.barLabelActive]} numberOfLines={1}>
                    {d.period}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </ScrollView>

      <View style={chart.footer}>
        <View style={chart.legend}>
          {employers.map((e, i) => (
            <View key={e.id} style={chart.legendItem}>
              <View style={[chart.legendDot, { backgroundColor: EMPLOYER_TINT[i % EMPLOYER_TINT.length] }]} />
              <Text style={chart.legendText}>{e.name}</Text>
            </View>
          ))}
        </View>
        <Text style={chart.baselineNote}>Index 100 = first salary slip · figures private by default</Text>
      </View>
    </View>
  );
}

const chart = StyleSheet.create({
  wrap: { backgroundColor: colors.surface3, borderRadius: 18, padding: 16, marginBottom: 4 },
  tooltip: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 14 },
  tooltipDot: { width: 10, height: 10, borderRadius: 5, marginTop: 6 },
  tooltipIndex: { fontFamily: fonts.displayBold, fontSize: 28, color: colors.ink, letterSpacing: -1 },
  tooltipIndexUnit: { fontFamily: fonts.mono, fontSize: 13, color: colors.ink3 },
  tooltipMeta: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  tooltipBadges: { alignItems: 'flex-end' },
  badge: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontFamily: fonts.bodySemiBold, fontSize: 10 },
  scroll: { marginHorizontal: -4 },
  barsArea: { position: 'relative' },
  guideLine: { position: 'absolute', left: 0, right: 0, flexDirection: 'row', alignItems: 'center' },
  guideLabel: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3, width: CHART_LEFT_PAD - 4, textAlign: 'right', paddingRight: 6 },
  guideRule: { flex: 1, height: 1, backgroundColor: 'rgba(0,0,0,0.06)' },
  bars: { flexDirection: 'row', alignItems: 'flex-end', height: CHART_H },
  barWrap: { alignItems: 'center', position: 'relative' },
  switchLine: { position: 'absolute', left: -1, top: 0, bottom: 20, width: 1.5, backgroundColor: 'rgba(99,102,241,0.3)', borderStyle: 'dashed' },
  barTrack: { justifyContent: 'flex-end', alignItems: 'center' },
  bar: { borderTopLeftRadius: 6, borderTopRightRadius: 6 },
  barInactive: { borderTopLeftRadius: 6, borderTopRightRadius: 6 },
  barLabel: { fontFamily: fonts.mono, fontSize: 8, color: colors.ink3, marginTop: 5, textAlign: 'center' },
  barLabelActive: { color: colors.ink, fontFamily: fonts.bodySemiBold },
  footer: { marginTop: 12, gap: 6 },
  legend: { flexDirection: 'row', gap: 14, flexWrap: 'wrap' },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { fontFamily: fonts.bodyRegular, fontSize: 11, color: colors.ink2 },
  baselineNote: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3 },
});

// ── Employer timeline ──────────────────────────────────────────────────────────
function Timeline({ employers, growthData }: { employers: Employer[]; growthData: GrowthPoint[] }) {
  return (
    <View style={tl.wrap}>
      <LinearGradient colors={[colors.indigo, colors.surface3]} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={tl.line} />
      {employers.map((emp, i) => {
        const isActive = emp.to === null;
        const ci = i % EMPLOYER_PALETTE.length;
        const empPoints = growthData.filter(d => d.employer_id === emp.id);
        const firstIdx = empPoints[0]?.index ?? 100;
        const lastIdx = empPoints[empPoints.length - 1]?.index ?? firstIdx;
        const indexGrowth = lastIdx - firstIdx;

        return (
          <View key={emp.id} style={tl.item}>
            {isActive ? (
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={tl.marker}>
                <Text style={{ fontSize: 13 }}>🏢</Text>
              </LinearGradient>
            ) : (
              <View style={[tl.marker, { backgroundColor: colors.surface3 }]}>
                <Text style={{ fontSize: 13 }}>🏢</Text>
              </View>
            )}
            <View style={tl.card}>
              <View style={tl.cardTop}>
                <View style={{ flex: 1 }}>
                  <Text style={tl.org}>{emp.name}</Text>
                  <Text style={tl.role}>{emp.role}</Text>
                </View>
                <View style={[tl.pill, isActive ? tl.pillActive : tl.pillAlumni]}>
                  <Text style={[tl.pillText, isActive ? tl.pillActiveText : tl.pillAlumniText]}>
                    {isActive ? 'CURRENT' : 'ALUMNI'}
                  </Text>
                </View>
              </View>
              <Text style={tl.dates}>
                {emp.from ? new Date(emp.from).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : '—'}
                {' → '}
                {emp.to ? new Date(emp.to).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : 'Present'}
              </Text>
              <View style={tl.statsRow}>
                <View style={tl.stat}>
                  <Text style={[tl.statVal, { color: colors.emerald }]}>+{indexGrowth}pts</Text>
                  <Text style={tl.statLabel}>salary growth</Text>
                </View>
                <View style={tl.stat}>
                  <Text style={tl.statVal}>{empPoints.length}</Text>
                  <Text style={tl.statLabel}>payslips</Text>
                </View>
              </View>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const tl = StyleSheet.create({
  wrap: { paddingLeft: 44, position: 'relative', marginBottom: 4 },
  line: { position: 'absolute', left: 15, top: 14, bottom: 8, width: 2, borderRadius: 1 },
  item: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 16, gap: 14 },
  marker: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', position: 'absolute', left: -44, top: 0, borderWidth: 2, borderColor: colors.surface },
  card: { flex: 1, backgroundColor: colors.surface3, borderRadius: 16, padding: 14 },
  cardTop: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 6 },
  org: { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink },
  role: { fontSize: 12, color: colors.ink2, marginTop: 1 },
  pill: { borderRadius: 8, paddingVertical: 3, paddingHorizontal: 10, marginLeft: 8, marginTop: 2 },
  pillActive: { backgroundColor: 'rgba(52,211,153,0.15)' },
  pillAlumni: { backgroundColor: 'rgba(0,0,0,0.06)' },
  pillText: { fontFamily: fonts.mono, fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  pillActiveText: { color: '#047857' },
  pillAlumniText: { color: colors.ink2 },
  dates: { fontFamily: fonts.mono, fontSize: 11, color: colors.ink3, marginBottom: 10 },
  statsRow: { flexDirection: 'row', gap: 0 },
  stat: { flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: 10, padding: 8, marginRight: 6 },
  statVal: { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink },
  statLabel: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3, marginTop: 1 },
});

const EV_COLORS: Record<string, string> = {
  promotion: colors.amber,
  join: colors.emerald,
  leave: colors.rose,
  increment: colors.indigo,
};

// ── Screen ────────────────────────────────────────────────────────────────────
export default function CareerScreen() {
  const [chartMode] = useState<ChartMode>('P');

  const { data, isLoading, isError } = useQuery<CareerData>({
    queryKey: ['vault', 'career'],
    queryFn: () => api.get<CareerData>('/vault/career'),
    staleTime: 5 * 60 * 1000,
  });

  const growthData = data?.growth_data ?? [];
  const employers = data?.employers ?? [];
  const events = data?.events ?? [];
  const maxGrowth = growthData.length > 0 ? Math.max(...growthData.map(d => d.index)) - 100 : 0;

  return (
    <View style={styles.screen}>
      <LinearGradient colors={gradTopBg.colors} locations={gradTopBg.locations} start={gradTopBg.start} end={gradTopBg.end} style={styles.header}>
        <SafeAreaView edges={['top']}>
          <Text style={styles.headerTitle}>Career</Text>
          <Text style={styles.headerSub}>
            {employers.length > 0
              ? `${employers.length} employer${employers.length !== 1 ? 's' : ''}  ·  ${growthData.length} salary data points`
              : 'No documents yet — upload salary slips to see your journey'}
          </Text>
        </SafeAreaView>
      </LinearGradient>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent} showsVerticalScrollIndicator={false}>
        {isLoading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator color={colors.indigo} />
            <Text style={styles.loadingText}>Loading your career journey…</Text>
          </View>
        ) : isError ? (
          <View style={styles.loadingWrap}>
            <Text style={styles.loadingText}>{tUi('CAREER_LOAD_FAILED')}</Text>
          </View>
        ) : (
          <>
            {/* Summary stats — no raw figures */}
            <View style={styles.summaryRow}>
              <View style={styles.summaryCard}>
                <Text style={[styles.summaryVal, { color: colors.emerald }]}>+{maxGrowth}%</Text>
                <Text style={styles.summaryLabel}>total growth</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryVal}>{employers.length}</Text>
                <Text style={styles.summaryLabel}>employers</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryVal}>{growthData.length}</Text>
                <Text style={styles.summaryLabel}>data points</Text>
              </View>
            </View>

            {growthData.length > 0 ? (
              <>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionLabel}>SALARY GROWTH INDEX</Text>
                </View>
                <GrowthChart data={growthData} employers={employers} mode={chartMode} />
              </>
            ) : (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyText}>Upload salary slips or increment letters to see your growth chart.</Text>
              </View>
            )}

            {employers.length > 0 && (
              <>
                <Text style={[styles.sectionLabel, { marginTop: 20 }]}>EMPLOYERS</Text>
                <Timeline employers={employers} growthData={growthData} />
              </>
            )}

            {events.length > 0 && (
              <>
                <Text style={[styles.sectionLabel, { marginTop: 20 }]}>CAREER EVENTS</Text>
                <View style={styles.eventsCard}>
                  {events.map((ev, i) => (
                    <View key={ev.id} style={[styles.eventRow, i === events.length - 1 && { borderBottomWidth: 0 }]}>
                      <View style={[styles.evDot, { backgroundColor: EV_COLORS[ev.type] ?? colors.ink3 }]} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.evLabel}>{ev.label}</Text>
                        {ev.at && (
                          <Text style={styles.evDate}>{new Date(ev.at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</Text>
                        )}
                      </View>
                    </View>
                  ))}
                </View>
              </>
            )}

            <View style={styles.privacyNote}>
              <Text style={styles.privacyText}>🔒  Salary figures processed by AI · Only growth indices stored · Raw data never persisted</Text>
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: 20, paddingBottom: 18 },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: '#FFFFFF', letterSpacing: -0.4, marginTop: 8 },
  headerSub: { fontFamily: fonts.mono, fontSize: 11, color: '#9CA8C9', marginTop: 3 },
  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 120 },
  loadingWrap: { paddingTop: 60, alignItems: 'center', gap: 12 },
  loadingText: { fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink3 },
  summaryRow: { flexDirection: 'row', gap: 10, marginBottom: 20 },
  summaryCard: { flex: 1, backgroundColor: colors.surface3, borderRadius: 14, padding: 12, alignItems: 'center' },
  summaryVal: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, letterSpacing: -0.3 },
  summaryLabel: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3, marginTop: 2 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2 },
  emptyCard: { backgroundColor: colors.surface3, borderRadius: 14, padding: 20, alignItems: 'center' },
  emptyText: { fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink3, textAlign: 'center', lineHeight: 20 },
  eventsCard: { backgroundColor: colors.surface3, borderRadius: 18, padding: 14 },
  eventRow: { flexDirection: 'row', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.05)', alignItems: 'flex-start' },
  evDot: { width: 10, height: 10, borderRadius: 5, marginTop: 3, flexShrink: 0 },
  evLabel: { fontSize: 13, color: colors.ink, fontFamily: fonts.bodySemiBold },
  evDate: { fontSize: 11, color: colors.ink3, marginTop: 2 },
  privacyNote: { marginTop: 20, backgroundColor: 'rgba(52,211,153,0.06)', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: 'rgba(52,211,153,0.15)' },
  privacyText: { fontFamily: fonts.mono, fontSize: 10, color: '#059669', textAlign: 'center', lineHeight: 16 },
});
