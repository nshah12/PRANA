/**
 * GamificationScreen — Career Score, Badges, and Streak.
 *
 * Privacy contract: score is insight-level only.
 * No raw salary, CTC, or PAN in any displayed value.
 */
import React, { useEffect, useRef } from 'react';
import {
  View, Text, ScrollView, Pressable, StyleSheet,
  Animated, ActivityIndicator,
} from 'react-native';
import { tUi } from '@/i18n';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts, gradJourney, radius } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface GamificationProfile {
  score: number;
  score_breakdown: {
    completeness_pts: number;
    freshness_pts: number;
    diversity_pts: number;
    engagement_pts: number;
  };
  badges: Badge[];
  streak: {
    current_streak_days: number;
    longest_streak_days: number;
  };
}

interface Badge {
  badge_key: string;
  badge_name: string;
  badge_icon: string;
  category: string;
  earned_at: string | null;
}

interface CatalogBadge extends Badge {
  badge_description: string;
  earned: boolean;
}

interface CoachingAction {
  action_id:     string;
  action_type:   string;   // REQUEST_DOC | SELF_UPLOAD | ENGAGE
  doc_type:      string | null;
  doc_period:    string | null;
  employer_name: string | null;
  score_impact:  number;
  pillar:        string;   // completeness | freshness | engagement
  priority:      number;
  cta:           string;   // REQUEST | UPLOAD | CHECKIN
  cta_route:     string | null;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useProfile() {
  return useQuery<GamificationProfile>({
    queryKey: ['gamification', 'profile'],
    queryFn: () => api.get<GamificationProfile>('/v1/gamification/profile'),
    staleTime: 60_000,
  });
}

function useCatalog() {
  return useQuery<{ catalog: CatalogBadge[] }>({
    queryKey: ['gamification', 'catalog'],
    queryFn: () => api.get<{ catalog: CatalogBadge[] }>('/v1/gamification/catalog'),
    staleTime: 5 * 60_000,
  });
}

function useCoaching() {
  return useQuery<{ coaching: CoachingAction[]; total: number }>({
    queryKey: ['gamification', 'coaching'],
    queryFn: () => api.get<{ coaching: CoachingAction[]; total: number }>('/v1/gamification/coaching'),
    staleTime: 5 * 60_000,
  });
}

function useCheckin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/v1/gamification/checkin'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gamification'] });
    },
  });
}

// ── Score Dial ────────────────────────────────────────────────────────────────

function ScoreDial({ score }: { score: number }) {
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(anim, {
      toValue: score,
      useNativeDriver: false,
      tension: 60,
      friction: 8,
    }).start();
  }, [score]);

  const label =
    score >= 80 ? tUi('GAMIFICATION_SCORE_LABEL_EXCELLENT') :
    score >= 60 ? tUi('GAMIFICATION_SCORE_LABEL_STRONG') :
    score >= 40 ? tUi('GAMIFICATION_SCORE_LABEL_GROWING') :
    score >= 20 ? tUi('GAMIFICATION_SCORE_LABEL_GETTING_STARTED') :
    tUi('GAMIFICATION_SCORE_LABEL_START_JOURNEY');

  return (
    <View style={styles.dialContainer}>
      <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} style={styles.dialGradient} start={gradJourney.start} end={gradJourney.end}>
        <Animated.Text style={styles.dialScore}>
          {anim.interpolate({ inputRange: [0, 100], outputRange: ['0', '100'] }).toString()}
        </Animated.Text>
        <Text style={styles.dialScoreNumber}>{score}</Text>
        <Text style={styles.dialLabel}>{label}</Text>
      </LinearGradient>
      <Text style={styles.dialSubtitle}>{tUi('GAMIFICATION_CAREER_SCORE_LABEL')}</Text>
    </View>
  );
}

// ── Score Breakdown ───────────────────────────────────────────────────────────

function ScoreBreakdown({ breakdown }: { breakdown: GamificationProfile['score_breakdown'] }) {
  const bars = [
    { label: tUi('GAMIFICATION_BAR_VAULT_COVERAGE'),  pts: breakdown.completeness_pts, max: 40, color: '#6366f1' },
    { label: tUi('GAMIFICATION_BAR_DOC_FRESHNESS'),   pts: breakdown.freshness_pts,    max: 30, color: '#059669' },
    { label: tUi('GAMIFICATION_BAR_DOC_DIVERSITY'),   pts: breakdown.diversity_pts,    max: 20, color: '#d97706' },
    { label: tUi('GAMIFICATION_BAR_ENGAGEMENT'),      pts: breakdown.engagement_pts,   max: 10, color: '#dc2626' },
  ];

  return (
    <View style={styles.breakdown}>
      <Text style={styles.sectionTitle}>{tUi('GAMIFICATION_SCORE_BREAKDOWN')}</Text>
      {bars.map(b => (
        <View key={b.label} style={styles.barRow}>
          <Text style={styles.barLabel}>{b.label}</Text>
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${(b.pts / b.max) * 100}%` as any, backgroundColor: b.color }]} />
          </View>
          <Text style={styles.barPts}>{b.pts}/{b.max}</Text>
        </View>
      ))}
    </View>
  );
}

// ── Streak Card ───────────────────────────────────────────────────────────────

function StreakCard({ streak, onCheckin, loading }: {
  streak: GamificationProfile['streak'];
  onCheckin: () => void;
  loading: boolean;
}) {
  const flame = streak.current_streak_days >= 30 ? '👑' :
                streak.current_streak_days >= 7  ? '⚡' :
                streak.current_streak_days >= 3  ? '🔥' : '🌱';

  return (
    <View style={styles.streakCard}>
      <View style={styles.streakLeft}>
        <Text style={styles.streakEmoji}>{flame}</Text>
        <View>
          <Text style={styles.streakDays}>{tUi('GAMIFICATION_STREAK_DAYS', { days: streak.current_streak_days })}</Text>
          <Text style={styles.streakBest}>{tUi('GAMIFICATION_STREAK_BEST', { days: streak.longest_streak_days })}</Text>
        </View>
      </View>
      <Pressable onPress={onCheckin} disabled={loading} style={styles.checkinBtn}>
        <Text style={styles.checkinBtnText}>{loading ? '…' : tUi('GAMIFICATION_CHECKIN_BUTTON')}</Text>
      </Pressable>
    </View>
  );
}

// ── Badge Shelf ───────────────────────────────────────────────────────────────

function BadgeShelf({ catalog }: { catalog: CatalogBadge[] }) {
  const earned  = catalog.filter(b => b.earned);
  const locked  = catalog.filter(b => !b.earned);

  return (
    <View style={styles.badgeSection}>
      {earned.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>{tUi('GAMIFICATION_EARNED_BADGES')}</Text>
          <View style={styles.badgeGrid}>
            {earned.map(b => (
              <View key={b.badge_key} style={[styles.badgeCard, styles.badgeEarned]}>
                <Text style={styles.badgeIcon}>{b.badge_icon}</Text>
                <Text style={styles.badgeName}>{b.badge_name}</Text>
              </View>
            ))}
          </View>
        </>
      )}

      {locked.length > 0 && (
        <>
          <Text style={[styles.sectionTitle, { marginTop: 20 }]}>{tUi('GAMIFICATION_LOCKED_BADGES')}</Text>
          <View style={styles.badgeGrid}>
            {locked.map(b => (
              <View key={b.badge_key} style={[styles.badgeCard, styles.badgeLocked]}>
                <Text style={[styles.badgeIcon, { opacity: 0.35 }]}>{b.badge_icon}</Text>
                <Text style={[styles.badgeName, { color: colors.ink3 }]}>{b.badge_name}</Text>
                <Text style={styles.badgeHint}>{b.badge_description}</Text>
              </View>
            ))}
          </View>
        </>
      )}
    </View>
  );
}

// ── Coaching Section ──────────────────────────────────────────────────────────

const PILLAR_COLOR: Record<string, string> = {
  completeness: '#6366f1',
  freshness:    '#059669',
  engagement:   '#d97706',
};

function CoachingSection({ actions }: { actions: CoachingAction[] }) {
  if (actions.length === 0) {
    return (
      <View style={styles.coachingCard}>
        <Text style={styles.sectionTitle}>{tUi('YOUR_NEXT_STEPS')}</Text>
        <Text style={styles.coachingEmpty}>{tUi('COACHING_EMPTY')}</Text>
      </View>
    );
  }

  return (
    <View style={styles.coachingCard}>
      <Text style={styles.sectionTitle}>{tUi('YOUR_NEXT_STEPS')}</Text>
      {actions.map((action) => {
        const accentColor = PILLAR_COLOR[action.pillar] ?? colors.indigo;
        const ctaLabel =
          action.cta === 'UPLOAD'  ? tUi('COACHING_CTA_UPLOAD') :
          action.cta === 'CHECKIN' ? tUi('COACHING_CTA_CHECKIN') :
          tUi('COACHING_CTA_REQUEST');

        return (
          <View key={action.action_id} style={styles.coachingRow}>
            <View style={[styles.coachingAccent, { backgroundColor: accentColor }]} />
            <View style={styles.coachingBody}>
              <Text style={styles.coachingDocType}>
                {action.doc_type?.replace(/_/g, ' ') ?? tUi('GAMIFICATION_DAILY_CHECKIN_LABEL')}
                {action.doc_period ? `  ·  ${action.doc_period}` : ''}
              </Text>
              {action.employer_name ? (
                <Text style={styles.coachingEmployer}>{action.employer_name}</Text>
              ) : null}
              <Text style={[styles.coachingImpact, { color: accentColor }]}>
                {tUi('COACHING_SCORE_IMPACT', { pts: action.score_impact })}
              </Text>
            </View>
            <Pressable
              style={[styles.coachingCta, { borderColor: accentColor }]}
              onPress={() => {
                if (action.cta_route) {
                  router.push(action.cta_route as any);
                }
              }}
            >
              <Text style={[styles.coachingCtaText, { color: accentColor }]}>{ctaLabel}</Text>
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function GamificationScreen() {
  const { data: profile, isLoading: profileLoading, error: profileError } = useProfile();
  const { data: catalog, isLoading: catalogLoading } = useCatalog();
  const { data: coachingData } = useCoaching();
  const checkin = useCheckin();

  if (profileLoading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color={colors.indigo} />
        <Text style={styles.loadingText}>{tUi('GAMIFICATION_LOADING')}</Text>
      </SafeAreaView>
    );
  }

  if (profileError || !profile) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.errorText}>{tUi('CAREER_SCORE_LOAD_FAILED')}</Text>
        <Text style={styles.errorSub}>{tUi('CHECK_CONNECTION')}</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <Text style={styles.header}>{tUi('GAMIFICATION_CAREER_SCORE_LABEL')}</Text>
        <Text style={styles.subheader}>{tUi('GAMIFICATION_SUBHEADER')}</Text>

        {/* Score Dial */}
        <ScoreDial score={profile.score} />

        {/* Streak */}
        <StreakCard
          streak={profile.streak}
          onCheckin={() => checkin.mutate()}
          loading={checkin.isPending}
        />

        {/* Score breakdown */}
        <ScoreBreakdown breakdown={profile.score_breakdown} />

        {/* Coaching: Your Next Steps */}
        <CoachingSection actions={coachingData?.coaching ?? []} />

        {/* Badge catalog */}
        {catalogLoading ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={colors.indigo} />
        ) : catalog ? (
          <BadgeShelf catalog={catalog.catalog} />
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root:          { flex: 1, backgroundColor: colors.surface },
  center:        { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  scroll:        { padding: 20, paddingBottom: 48 },
  header:        { fontSize: 24, fontFamily: fonts.displayBold, color: colors.ink, marginBottom: 4 },
  subheader:     { fontSize: 13, color: colors.ink3, marginBottom: 24 },
  loadingText:   { marginTop: 12, color: colors.ink3, fontFamily: fonts.bodyRegular },
  errorText:     { fontSize: 16, color: colors.ink, fontFamily: fonts.bodySemiBold },
  errorSub:      { marginTop: 8, color: colors.ink3, fontFamily: fonts.bodyRegular },

  // Dial
  dialContainer: { alignItems: 'center', marginBottom: 24 },
  dialGradient:  { width: 140, height: 140, borderRadius: 70, alignItems: 'center', justifyContent: 'center' },
  dialScore:     { display: 'none' },
  dialScoreNumber: { fontSize: 48, fontFamily: fonts.displayBold, color: '#fff' },
  dialLabel:     { fontSize: 13, color: 'rgba(255,255,255,0.85)', fontFamily: fonts.bodyMedium, marginTop: 2 },
  dialSubtitle:  { marginTop: 10, fontSize: 13, color: colors.ink3, fontFamily: fonts.bodyRegular },

  // Streak
  streakCard:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                   backgroundColor: colors.surface3, borderRadius: radius.lg,
                   padding: 16, marginBottom: 20 },
  streakLeft:    { flexDirection: 'row', alignItems: 'center', gap: 12 },
  streakEmoji:   { fontSize: 32 },
  streakDays:    { fontSize: 16, fontFamily: fonts.bodySemiBold, color: colors.ink },
  streakBest:    { fontSize: 12, color: colors.ink3, marginTop: 2 },
  checkinBtn:    { backgroundColor: colors.indigo, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 },
  checkinBtnText: { color: '#fff', fontFamily: fonts.bodySemiBold, fontSize: 13 },

  // Breakdown
  breakdown:     { backgroundColor: colors.surface3, borderRadius: radius.lg, padding: 16, marginBottom: 20 },
  sectionTitle:  { fontSize: 15, fontFamily: fonts.bodySemiBold, color: colors.ink, marginBottom: 14 },
  barRow:        { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  barLabel:      { width: 110, fontSize: 12, color: colors.ink3 },
  barTrack:      { flex: 1, height: 8, backgroundColor: 'rgba(20,23,31,0.08)', borderRadius: 4, overflow: 'hidden', marginHorizontal: 8 },
  barFill:       { height: '100%', borderRadius: 4 },
  barPts:        { width: 36, fontSize: 11, color: colors.ink3, textAlign: 'right' },

  // Coaching
  coachingCard:     { backgroundColor: colors.surface3, borderRadius: radius.lg, padding: 16, marginBottom: 20 },
  coachingEmpty:    { fontSize: 13, color: colors.ink3, fontFamily: fonts.bodyRegular, lineHeight: 20 },
  coachingRow:      { flexDirection: 'row', alignItems: 'center', marginBottom: 14, gap: 10 },
  coachingAccent:   { width: 3, height: 44, borderRadius: 2 },
  coachingBody:     { flex: 1 },
  coachingDocType:  { fontSize: 13, fontFamily: fonts.bodySemiBold, color: colors.ink },
  coachingEmployer: { fontSize: 11, color: colors.ink3, marginTop: 1 },
  coachingImpact:   { fontSize: 11, fontFamily: fonts.bodySemiBold, marginTop: 2 },
  coachingCta:      { borderWidth: 1.5, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 5 },
  coachingCtaText:  { fontSize: 12, fontFamily: fonts.bodySemiBold },

  // Badges
  badgeSection:  { marginBottom: 20 },
  badgeGrid:     { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  badgeCard:     { width: '30%', borderRadius: radius.lg, padding: 12, alignItems: 'center' },
  badgeEarned:   { backgroundColor: colors.surface3, borderWidth: 1.5, borderColor: colors.indigo },
  badgeLocked:   { backgroundColor: colors.surface3, borderWidth: 1, borderColor: 'rgba(20,23,31,0.08)' },
  badgeIcon:     { fontSize: 26, marginBottom: 6 },
  badgeName:     { fontSize: 11, fontFamily: fonts.bodySemiBold, color: colors.ink, textAlign: 'center' },
  badgeHint:     { fontSize: 10, color: colors.ink3, textAlign: 'center', marginTop: 4, lineHeight: 13 },
});
