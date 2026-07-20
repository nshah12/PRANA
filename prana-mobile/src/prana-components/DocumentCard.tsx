/**
 * DocumentCard — the atomic unit of the vault list.
 *
 * Source identity is the most important visual signal on each card.
 * At a glance the employee must know WHO gave them this document:
 *
 *   🛡  Employer pushed   → emerald  "NPCI pushed this"  — verified, authoritative
 *   📧  From email        → cyan     "Fetched from Gmail" — auto-captured
 *   ⬆   Self-uploaded     → amber    "You uploaded this"  — you own the chain
 *   ✦   Third-party       → indigo   "Verified externally"
 *
 * Actions per card (outside selection mode): View · Download · Share
 * Selection mode (long-press): checkbox top-left, entire card is tappable
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, fonts, radius, docIconGradients } from '../prana-theme/tokens';
import type { DocSourceType } from '../hooks/useVault';

export type DocIconType = keyof typeof docIconGradients;

// Re-export so callers don't need to import from hooks
export type { DocSourceType };

// ── Source metadata ───────────────────────────────────────────────────────────
export const SOURCE_META: Record<DocSourceType, {
  icon: string;
  label: string;       // short: shown on card
  color: string;       // text / icon colour
  bg: string;          // badge background
  border: string;      // badge border
}> = {
  EMPLOYER_PUSH: {
    icon: '🛡',
    label: 'Employer',
    color: '#059669',
    bg: 'rgba(52,211,153,0.12)',
    border: 'rgba(52,211,153,0.25)',
  },
  EMAIL_FETCH: {
    icon: '📧',
    label: 'Email',
    color: '#0891B2',
    bg: 'rgba(34,211,238,0.10)',
    border: 'rgba(34,211,238,0.22)',
  },
  EMPLOYEE_SELF_UPLOAD: {
    icon: '⬆',
    label: 'Self',
    color: '#B45309',
    bg: 'rgba(251,191,36,0.12)',
    border: 'rgba(251,191,36,0.25)',
  },
  THIRD_PARTY_VERIFIED: {
    icon: '✦',
    label: '3rd party',
    color: '#4338CA',
    bg: 'rgba(99,102,241,0.12)',
    border: 'rgba(99,102,241,0.25)',
  },
};

interface DocumentCardProps {
  id: string;
  iconType: DocIconType;
  iconEmoji: string;
  title: string;
  issuer: string;           // company name or "Self" / "Gmail"
  docType: string;          // human-readable doc type label
  sourceType: DocSourceType;
  receivedAt: string;       // ISO date string
  highlighted?: boolean;
  // Selection mode
  selectionMode?: boolean;
  selected?: boolean;
  onPress?: () => void;
  onLongPress?: () => void;
  // Actions
  onView?: () => void;
  onDownload?: () => void;
  onShare?: () => void;
}

export function DocumentCard({
  iconType, iconEmoji, title, issuer, docType, sourceType, receivedAt,
  highlighted = false,
  selectionMode = false,
  selected = false,
  onPress, onLongPress,
  onView, onDownload, onShare,
}: DocumentCardProps) {
  const iconGrad = docIconGradients[iconType] ?? docIconGradients.salary;
  const src = SOURCE_META[sourceType] ?? SOURCE_META.EMPLOYER_PUSH;

  const date = new Date(receivedAt);
  const calMonth = date.toLocaleString('en', { month: 'short' }).toUpperCase();
  const calDay   = String(date.getDate()).padStart(2, '0');

  return (
    <Pressable
      style={[
        styles.card,
        highlighted  && styles.cardHighlighted,
        selected     && styles.cardSelected,
      ]}
      onPress={selectionMode ? onPress : onView}
      onLongPress={onLongPress}
      delayLongPress={350}
    >
      {/* Selection checkbox */}
      {selectionMode && (
        <View style={[styles.checkbox, selected && styles.checkboxOn]}>
          {selected && <Text style={styles.checkmark}>✓</Text>}
        </View>
      )}

      {/* Left — gradient doc-type icon */}
      <LinearGradient
        colors={iconGrad.colors}
        start={iconGrad.start}
        end={iconGrad.end}
        style={styles.icon}
      >
        <Text style={styles.iconEmoji}>{iconEmoji}</Text>
      </LinearGradient>

      {/* Right — content column */}
      <View style={styles.body}>

        {/* Row 1: title */}
        <Text style={styles.title} numberOfLines={1}>{title}</Text>

        {/* Row 2: issuer · doc type */}
        <Text style={styles.meta} numberOfLines={1}>
          {issuer}  ·  {docType}
        </Text>

        {/* Row 3: source badge + date chip + actions */}
        <View style={styles.bottomRow}>

          {/* Source badge — the key identity signal */}
          <View style={[styles.sourceBadge, { backgroundColor: src.bg, borderColor: src.border }]}>
            <Text style={styles.sourceIcon}>{src.icon}</Text>
            <Text style={[styles.sourceLabel, { color: src.color }]}>{src.label}</Text>
          </View>

          {/* Cal chip */}
          <View style={styles.calChip}>
            <View style={styles.calMonthBg}>
              <Text style={styles.calMonthText}>{calMonth}</Text>
            </View>
            <View style={styles.calDayBg}>
              <Text style={styles.calDayText}>{calDay}</Text>
            </View>
          </View>

          {/* Action icons — hidden in selection mode */}
          {!selectionMode && (
            <View style={styles.actions}>
              <ActionBtn icon="👁" onPress={onView}     label="View" />
              <ActionBtn icon="⬇" onPress={onDownload} label="Download" />
              <ActionBtn icon="↗" onPress={onShare}    label="Share" />
            </View>
          )}
        </View>
      </View>
    </Pressable>
  );
}

function ActionBtn({ icon, onPress, label }: { icon: string; onPress?: () => void; label: string }) {
  return (
    <Pressable
      style={styles.actionBtn}
      onPress={onPress}
      hitSlop={{ top: 8, bottom: 8, left: 6, right: 6 }}
      accessibilityLabel={label}
    >
      <Text style={styles.actionIcon}>{icon}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: colors.surface3,
    borderRadius: radius.lg,
    padding: 12,
    marginBottom: 10,
    gap: 12,
    borderWidth: 1.5,
    borderColor: 'transparent',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1,
  },
  cardHighlighted: { borderColor: 'rgba(99,102,241,0.4)' },
  cardSelected: { borderColor: colors.indigo, backgroundColor: 'rgba(99,102,241,0.06)' },

  // Checkbox
  checkbox: {
    position: 'absolute', top: 10, left: 10, zIndex: 2,
    width: 22, height: 22, borderRadius: 6,
    borderWidth: 2, borderColor: colors.ink3,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxOn: { backgroundColor: colors.indigo, borderColor: colors.indigo },
  checkmark: { fontSize: 12, color: '#FFFFFF', fontWeight: '700' },

  // Doc-type icon
  icon: {
    width: 46, height: 46, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center',
    flexShrink: 0,
    shadowColor: '#000', shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.18, shadowRadius: 6, elevation: 3,
  },
  iconEmoji: { fontSize: 20 },

  // Content
  body: { flex: 1, minWidth: 0 },
  title: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 2 },
  meta:  { fontFamily: fonts.bodyRegular,  fontSize: 11, color: colors.ink3, marginBottom: 7 },

  bottomRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },

  // Source badge — the identity signal
  sourceBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: 8, borderWidth: 1,
  },
  sourceIcon:  { fontSize: 10 },
  sourceLabel: { fontFamily: fonts.mono, fontSize: 9, fontWeight: '700', letterSpacing: 0.3 },

  // Cal chip
  calChip: {
    width: 32, height: 32, borderRadius: 8, overflow: 'hidden',
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.07)',
  },
  calMonthBg:   { backgroundColor: colors.rose, paddingVertical: 2, alignItems: 'center' },
  calMonthText: { fontFamily: fonts.mono, fontSize: 7, fontWeight: '700', color: '#FFFFFF', letterSpacing: 0.3 },
  calDayBg:     { flex: 1, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' },
  calDayText:   { fontFamily: fonts.displayBold, fontSize: 13, color: colors.ink },

  // Actions
  actions: { flexDirection: 'row', gap: 6, marginLeft: 'auto' },
  actionBtn: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.07)',
    alignItems: 'center', justifyContent: 'center',
  },
  actionIcon: { fontSize: 12 },
});
