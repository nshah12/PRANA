import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Modal, Pressable } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

// ── Single-doc download toast ─────────────────────────────────────
export function useDownloadToast() {
  const [toast, setToast] = useState<string | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;

  function showDownload(title: string) {
    setToast(title);
    Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      Animated.delay(1800),
      Animated.timing(opacity, { toValue: 0, duration: 300, useNativeDriver: true }),
    ]).start(() => setToast(null));
  }

  const ToastUI = toast ? (
    <Animated.View style={[toastStyles.wrap, { opacity }]} pointerEvents="none">
      <View style={toastStyles.pill}>
        <Text style={toastStyles.icon}>⬇</Text>
        <View>
          <Text style={toastStyles.title}>Downloading…</Text>
          <Text style={toastStyles.sub} numberOfLines={1}>{toast}</Text>
        </View>
        <View style={toastStyles.spinner}>
          <Text style={toastStyles.spinnerText}>✓</Text>
        </View>
      </View>
    </Animated.View>
  ) : null;

  return { showDownload, ToastUI };
}

const toastStyles = StyleSheet.create({
  wrap: { position: 'absolute', bottom: 110, left: 16, right: 16, zIndex: 999 },
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.space, borderRadius: 16, padding: 14,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)',
    shadowColor: '#000', shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4, shadowRadius: 16, elevation: 10,
  },
  icon: { fontSize: 18 },
  title: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: '#FFFFFF' },
  sub: { fontFamily: fonts.mono, fontSize: 10, color: '#8B93A7', marginTop: 1, maxWidth: 220 },
  spinner: { marginLeft: 'auto', width: 24, height: 24, borderRadius: 12, backgroundColor: colors.emerald, alignItems: 'center', justifyContent: 'center' },
  spinnerText: { fontSize: 12, color: '#FFFFFF', fontWeight: '700' },
});

// ── ZIP progress modal ────────────────────────────────────────────
interface ZipModalProps {
  visible: boolean;
  count: number;
  onDone: () => void;
}

export function ZipModal({ visible, count, onDone }: ZipModalProps) {
  const progress = useRef(new Animated.Value(0)).current;
  const [phase, setPhase] = useState<'packing' | 'done'>('packing');

  useEffect(() => {
    if (!visible) { progress.setValue(0); setPhase('packing'); return; }
    setPhase('packing');
    Animated.timing(progress, {
      toValue: 1, duration: 1600, useNativeDriver: false,
    }).start(() => setPhase('done'));
  }, [visible]);

  const barWidth = progress.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDone}>
      <View style={zip.overlay}>
        <View style={zip.card}>
          {phase === 'packing' ? (
            <>
              <Text style={zip.emoji}>📦</Text>
              <Text style={zip.title}>Packing {count} document{count !== 1 ? 's' : ''}…</Text>
              <Text style={zip.sub}>Encrypting and bundling into a ZIP file</Text>
              <View style={zip.trackWrap}>
                <Animated.View style={[zip.track]}>
                  <Animated.View style={{ width: barWidth }}>
                    <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={zip.bar} />
                  </Animated.View>
                </Animated.View>
              </View>
            </>
          ) : (
            <>
              <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={zip.doneCircle}>
                <Text style={zip.doneIcon}>✓</Text>
              </LinearGradient>
              <Text style={zip.title}>Ready to download</Text>
              <Text style={zip.sub}>prana-vault-{count}docs.zip · {(count * 0.3).toFixed(1)} MB</Text>
              <Pressable onPress={onDone}>
                <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={zip.doneBtn}>
                  <Text style={zip.doneBtnText}>⬇  Download ZIP</Text>
                </LinearGradient>
              </Pressable>
              <Pressable style={zip.cancelBtn} onPress={onDone}>
                <Text style={zip.cancelText}>Cancel</Text>
              </Pressable>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

const zip = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center', padding: 24 },
  card: { backgroundColor: colors.surface, borderRadius: 24, padding: 28, width: '100%', alignItems: 'center', gap: 10 },
  emoji: { fontSize: 44, marginBottom: 4 },
  title: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.ink, textAlign: 'center', letterSpacing: -0.2 },
  sub: { fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink3, textAlign: 'center' },
  trackWrap: { width: '100%', marginTop: 8 },
  track: { height: 8, backgroundColor: colors.surface3, borderRadius: 4, overflow: 'hidden', width: '100%' },
  bar: { height: 8, borderRadius: 4 },
  doneCircle: { width: 64, height: 64, borderRadius: 20, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  doneIcon: { fontSize: 28, color: '#04261C', fontWeight: '700' },
  doneBtn: { borderRadius: 16, width: '100%', marginTop: 8 },
  doneBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C', textAlign: 'center', padding: 16 },
  cancelBtn: { padding: 10 },
  cancelText: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink3 },
});
