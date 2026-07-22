// src/components/StatCard.tsx
//
// Translates .stat-card / .stat-card .num / .stat-card .lbl

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme/tokens';

interface StatCardProps {
  value: string | number;
  label: string;
  accent: 'indigo' | 'emerald';
}

export function StatCard({ value, label, accent }: StatCardProps) {
  return (
    <View style={styles.card}>
      <Text style={[styles.num, { color: accent === 'indigo' ? colors.indigo : '#10B981' }]}>
        {value}
      </Text>
      <Text style={styles.lbl}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  // .stat-card
  card: {
    flex: 1,
    backgroundColor: colors.surface2, // #FFFFFF
    borderRadius: radius.lg, // 18
    padding: 16,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.04)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 1,
  },
  // .stat-card .num
  num: {
    fontFamily: fonts.displayBold,
    fontSize: 26,
    letterSpacing: -0.5,
  },
  // .stat-card .lbl
  lbl: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    color: colors.ink3,
    marginTop: 2,
  },
});
