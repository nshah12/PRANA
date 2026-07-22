// src/components/DocumentCard.tsx
//
// Translates .doc-card + .doc-icon + .cal-chip + .provenance from the HTML
// prototype. This is the highest-complexity component in Vault Home --
// gradients, a two-tone "calendar" chip, and a circular provenance badge.

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, fonts, radius, docIconGradients } from '../theme/tokens';

export type DocIconType = keyof typeof docIconGradients; // 'salary' | 'form16' | 'invest'
export type Provenance = 'employer' | 'self' | 'thirdparty';

interface DocumentCardProps {
  iconType: DocIconType;
  iconEmoji: string; // 💰 / 🧾 / 📊 -- prototype used emoji as icon placeholders
  title: string;
  meta: string;
  calMonth: string; // "JUN"
  calDay: string; // "02"
  dateLabel: string; // "Received" | "Uploaded"
  provenance: Provenance;
  highlighted?: boolean; // screen 17: new-document highlight border
}

// .provenance.employer / .self / .thirdparty
const PROVENANCE_CONFIG: Record<
  Provenance,
  { bg: string; color: string; icon: string; label: string }
> = {
  employer: { bg: 'rgba(52,211,153,0.15)', color: '#047857', icon: '🛡', label: 'Pushed by employer' },
  self: { bg: 'rgba(251,191,36,0.18)', color: '#92400E', icon: '⬆', label: 'Self-uploaded — unverified' },
  thirdparty: { bg: 'rgba(99,102,241,0.15)', color: '#4338CA', icon: '✓', label: 'Third-party verified' },
};

export function DocumentCard({
  iconType,
  iconEmoji,
  title,
  meta,
  calMonth,
  calDay,
  dateLabel,
  provenance,
  highlighted = false,
}: DocumentCardProps) {
  const prov = PROVENANCE_CONFIG[provenance];
  const iconGrad = docIconGradients[iconType];

  return (
    <View style={[styles.card, highlighted && styles.cardHighlighted]}>
      {/* .doc-icon -- LinearGradient since RN has no CSS gradient backgrounds */}
      <LinearGradient
        colors={iconGrad.colors}
        start={iconGrad.start}
        end={iconGrad.end}
        style={styles.icon}
      >
        <Text style={styles.iconEmoji}>{iconEmoji}</Text>
      </LinearGradient>

      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        <Text style={styles.meta} numberOfLines={1}>
          {meta}
        </Text>

        <View style={styles.bottomRow}>
          <View style={styles.leftGroup}>
            {/* .cal-chip -- two-tone "calendar" block (no gradient needed, just stacked colors) */}
            <View style={styles.calChip}>
              <View style={styles.calMonth}>
                <Text style={styles.calMonthText}>{calMonth}</Text>
              </View>
              <View style={styles.calDay}>
                <Text style={styles.calDayText}>{calDay}</Text>
              </View>
            </View>
            <Text style={styles.dateLabel}>{dateLabel}</Text>
          </View>

          {/* .provenance -- circular badge, color varies by source */}
          <View
            style={[styles.provenance, { backgroundColor: prov.bg }]}
            accessibilityLabel={prov.label}
          >
            <Text style={[styles.provenanceIcon, { color: prov.color }]}>{prov.icon}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // .doc-card
  card: {
    flexDirection: 'row',
    backgroundColor: colors.surface3, // #F0EFEA
    borderRadius: radius.lg, // 18
    padding: 12,
    marginBottom: 10,
    gap: 12,
    // CSS box-shadow -> RN shadow* (iOS) + elevation (Android)
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1,
  },
  // screen 17: highlighted "new document" card -- subtle indigo border
  cardHighlighted: {
    borderWidth: 1.5,
    borderColor: 'rgba(99,102,241,0.3)',
  },
  // .doc-icon (44x44, radius 13, font-size 20)
  icon: {
    width: 44,
    height: 44,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 6,
    elevation: 3,
  },
  iconEmoji: {
    fontSize: 20,
  },
  // .doc-info { flex: 1; min-width: 0 }
  info: {
    flex: 1,
    // RN flex children shrink by default -- no min-width:0 hack needed
  },
  // .doc-title
  title: {
    fontFamily: fonts.bodySemiBold,
    fontSize: 13,
    color: colors.ink,
    marginBottom: 2,
  },
  // .doc-meta
  meta: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    color: colors.ink3,
    marginBottom: 2,
  },
  // .doc-bottom-row
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 8,
    gap: 8,
  },
  leftGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
    minWidth: 0,
  },
  // .cal-chip (38x38, radius 10, overflow:hidden -> children clip to border radius)
  calChip: {
    width: 38,
    height: 38,
    borderRadius: 10,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 3,
    elevation: 2,
  },
  // .cal-chip .cal-month
  calMonth: {
    backgroundColor: colors.rose,
    paddingVertical: 2,
    alignItems: 'center',
  },
  calMonthText: {
    fontFamily: fonts.mono,
    fontSize: 9,
    fontWeight: '700',
    color: '#FFFFFF',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  // .cal-chip .cal-day
  calDay: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  calDayText: {
    fontFamily: fonts.displayBold,
    fontSize: 16,
    color: colors.ink,
  },
  dateLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    color: colors.ink3,
  },
  // .provenance (28x28 circle)
  provenance: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  provenanceIcon: {
    fontSize: 14,
  },
});
