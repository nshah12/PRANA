import React from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { colors, fonts } from '@/prana-theme/tokens';

interface PageScreenProps {
  title: string;
  sub?: string;
  icon?: string;
  rightIcon?: string;
  onRightPress?: () => void;
  children: React.ReactNode;
  scrollable?: boolean;
}

export function PageScreen({ title, sub, icon, rightIcon, onRightPress, children, scrollable = true }: PageScreenProps) {
  return (
    <View style={styles.screen}>
      <SafeAreaView edges={['top']} style={styles.safe}>
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>{title}</Text>
            {sub ? <Text style={styles.sub}>{sub}</Text> : null}
          </View>
          <View style={styles.headerRight}>
            {icon ? <View style={styles.phIcon}><Text>{icon}</Text></View> : null}
            {rightIcon ? (
              <Pressable style={styles.phIcon} onPress={onRightPress}>
                <Text>{rightIcon}</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      </SafeAreaView>
      {scrollable ? (
        <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent} showsVerticalScrollIndicator={false}>
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.body, styles.bodyContent]}>{children}</View>
      )}
    </View>
  );
}

export function SectionLabel({ label }: { label: string }) {
  return <Text style={styles.sectionLabel}>{label}</Text>;
}

export function TlCard({ children }: { children: React.ReactNode }) {
  return <View style={styles.tlCard}>{children}</View>;
}

export function TlRow({ dot, text, time }: { dot: string; text: string; time: string }) {
  return (
    <View style={styles.tlRow}>
      <View style={[styles.tlDot, { backgroundColor: dot }]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.tlText}>{text}</Text>
        <Text style={styles.tlTime}>{time}</Text>
      </View>
    </View>
  );
}

export function FormCard({ children }: { children: React.ReactNode }) {
  return <View style={styles.formCard}>{children}</View>;
}

export function FormLabel({ label }: { label: string }) {
  return <Text style={styles.formLabel}>{label}</Text>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  safe: { backgroundColor: colors.surface },
  header: {
    flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8,
  },
  title: { fontFamily: fonts.displayBold, fontSize: 24, color: colors.ink, letterSpacing: -0.3, marginBottom: 3 },
  sub: { fontSize: 12, color: colors.ink2, lineHeight: 18 },
  headerRight: { flexDirection: 'row', gap: 8 },
  phIcon: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: colors.surface3,
    alignItems: 'center', justifyContent: 'center',
  },
  body: { flex: 1 },
  bodyContent: { paddingHorizontal: 19, paddingTop: 8, paddingBottom: 104 },
  sectionLabel: {
    fontFamily: fonts.mono, fontSize: 11, fontWeight: '700', color: colors.ink3,
    textTransform: 'uppercase', letterSpacing: 1.3, marginBottom: 10, marginTop: 16,
  },
  tlCard: { backgroundColor: colors.surface3, borderRadius: 18, padding: 14, marginBottom: 10 },
  tlRow: { flexDirection: 'row', gap: 10, paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.04)' },
  tlDot: { width: 10, height: 10, borderRadius: 5, marginTop: 3, flexShrink: 0 },
  tlText: { fontSize: 12, color: colors.ink, lineHeight: 18 },
  tlTime: { fontSize: 10, color: colors.ink3, marginTop: 2 },
  formCard: { backgroundColor: colors.surface3, borderRadius: 18, padding: 14, marginBottom: 10 },
  formLabel: {
    fontFamily: fonts.mono, fontSize: 11, color: colors.ink3,
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
  },
});
