/**
 * Splash screen — first thing a user ever sees.
 *
 * Visual metaphor: documents from multiple employers (nodes orbiting)
 * converge into ONE vault that belongs to the employee.
 * Message: "Your career follows YOU. Not your employer."
 *
 * Sequence:
 *   0.0s  background fades in
 *   0.4s  employer nodes appear one by one (spring)
 *   1.4s  connection lines draw from nodes to vault center
 *   2.0s  vault icon blooms at center
 *   2.6s  tagline fades + slides up
 *   3.4s  navigate (authenticated → vault, device credential → biometric, else → sign-in)
 */
import React, { useEffect, useRef } from 'react';
import { View, Text, Animated, StyleSheet, Easing, Dimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';

const { width: W } = Dimensions.get('window');
const CX = W / 2;   // center x
const CY = 220;     // center y of illustration

// Employer node positions — circle of radius 100 around vault
const ORBIT_R = 96;
const NODES = [
  { emoji: '🏢', label: 'Infosys',  angle: -90 },
  { emoji: '🏦', label: 'NPCI',     angle:  -10 },
  { emoji: '💼', label: 'Wipro',    angle:   70 },
  { emoji: '📋', label: 'Form 16',  angle:  150 },
  { emoji: '🧾', label: 'Payslip',  angle:  210 },
];

function toXY(angle: number, r: number) {
  const rad = (angle * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

function ConstellationNode({
  emoji, angle, delay, vaultScale,
}: {
  emoji: string; angle: number; delay: number; vaultScale: Animated.Value;
}) {
  const scale   = useRef(new Animated.Value(0)).current;
  const lineLen = useRef(new Animated.Value(0)).current;
  const { x, y } = toXY(angle, ORBIT_R);

  useEffect(() => {
    setTimeout(() => {
      Animated.spring(scale, { toValue: 1, friction: 5, tension: 220, useNativeDriver: true }).start();
    }, delay);
    setTimeout(() => {
      Animated.timing(lineLen, { toValue: 1, duration: 400, easing: Easing.out(Easing.quad), useNativeDriver: false }).start();
    }, delay + 200);
  }, []);

  // Line from node toward vault center
  const dx = CX - x;
  const dy = CY - y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const lineAngle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const lineW = lineLen.interpolate({ inputRange: [0, 1], outputRange: [0, dist - 28] });

  return (
    <>
      {/* Connection line */}
      <Animated.View
        style={{
          position: 'absolute',
          left: x + 14,
          top: y + 14,
          width: lineW,
          height: 1,
          backgroundColor: 'rgba(99,102,241,0.25)',
          transformOrigin: 'left',
          transform: [{ rotate: `${lineAngle}deg` }],
        }}
      />
      {/* Node */}
      <Animated.View style={[
        styles.node,
        { left: x, top: y, transform: [{ scale }] },
      ]}>
        <Text style={styles.nodeEmoji}>{emoji}</Text>
      </Animated.View>
    </>
  );
}

function VaultCenter({ scale }: { scale: Animated.Value }) {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.08, duration: 1400, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1.00, duration: 1400, useNativeDriver: true }),
      ])
    );
    // Start pulse after bloom
    setTimeout(() => loop.start(), 2200);
    return () => loop.stop();
  }, []);

  const glowOpacity = pulse.interpolate({ inputRange: [1, 1.08], outputRange: [0.25, 0.55] });

  return (
    <Animated.View style={[
      styles.vaultWrap,
      { left: CX - 34, top: CY - 34, transform: [{ scale }] },
    ]}>
      {/* Glow ring */}
      <Animated.View style={[styles.vaultGlow, { opacity: glowOpacity, transform: [{ scale: pulse }] }]} />
      {/* Icon */}
      <LinearGradient
        colors={gradJourney.colors}
        locations={gradJourney.locations}
        start={gradJourney.start}
        end={gradJourney.end}
        style={styles.vaultGrad}
      >
        <Text style={styles.vaultEmoji}>🔐</Text>
      </LinearGradient>
    </Animated.View>
  );
}

export default function SplashScreen() {
  const { isAuthenticated, hasDeviceCredential } = useAuth() as any;
  const vaultScale   = useRef(new Animated.Value(0)).current;
  const taglineOpacity = useRef(new Animated.Value(0)).current;
  const taglineY     = useRef(new Animated.Value(16)).current;
  const subOpacity   = useRef(new Animated.Value(0)).current;
  const bgOpacity    = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Background fade
    Animated.timing(bgOpacity, { toValue: 1, duration: 600, useNativeDriver: true }).start();

    // Vault bloom at 2.0s
    setTimeout(() => {
      Animated.spring(vaultScale, { toValue: 1, friction: 4, tension: 160, useNativeDriver: true }).start();
    }, 2000);

    // Tagline at 2.6s
    setTimeout(() => {
      Animated.parallel([
        Animated.timing(taglineOpacity, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(taglineY, { toValue: 0, duration: 700, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      ]).start();
    }, 2600);

    // Sub-tagline at 3.0s
    setTimeout(() => {
      Animated.timing(subOpacity, { toValue: 1, duration: 600, useNativeDriver: true }).start();
    }, 3000);

    // Navigate at 4.0s
    const navTimer = setTimeout(() => {
      if (isAuthenticated) {
        router.replace('/(vault)/vault');
      } else if (hasDeviceCredential) {
        router.replace('/(auth)/biometric-unlock');
      } else {
        router.replace('/(auth)/sign-in');
      }
    }, 4000);

    return () => clearTimeout(navTimer);
  }, []);

  return (
    <Animated.View style={[styles.screen, { opacity: bgOpacity }]}>
      <LinearGradient
        colors={['#080D1A', '#0F172A', '#131B33']}
        locations={[0, 0.5, 1]}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      {/* Ambient glow orbs */}
      <View style={styles.orbLeft} pointerEvents="none" />
      <View style={styles.orbRight} pointerEvents="none" />

      <SafeAreaView style={styles.safe}>
        {/* Constellation illustration */}
        <View style={styles.illustration}>
          {NODES.map((n, i) => (
            <ConstellationNode
              key={n.label}
              emoji={n.emoji}
              angle={n.angle}
              delay={400 + i * 200}
              vaultScale={vaultScale}
            />
          ))}
          <VaultCenter scale={vaultScale} />

          {/* "YOUR VAULT" label under vault */}
          <Animated.View style={[styles.vaultLabel, { top: CY + 46, opacity: vaultScale }]}>
            <Text style={styles.vaultLabelText}>YOUR VAULT</Text>
          </Animated.View>
        </View>

        {/* Copy */}
        <View style={styles.copyBlock}>
          <Animated.Text style={[styles.tagline, {
            opacity: taglineOpacity,
            transform: [{ translateY: taglineY }],
          }]}>
            Your career{'\n'}
            <Text style={styles.taglineAccent}>follows you now.</Text>
          </Animated.Text>

          <Animated.Text style={[styles.sub, { opacity: subOpacity }]}>
            Every document from every employer — in one vault that belongs to you alone.
          </Animated.Text>

          {/* Loading dots */}
          <Animated.View style={[styles.dotsRow, { opacity: subOpacity }]}>
            {[0, 1, 2].map(i => (
              <BounceDot key={i} delay={i * 200} />
            ))}
          </Animated.View>
        </View>

        {/* Brand watermark */}
        <View style={styles.brand}>
          <LinearGradient colors={gradJourney.colors} locations={gradJourney.locations} start={gradJourney.start} end={gradJourney.end} style={styles.brandMark}>
            <Text style={styles.brandIcon}>P</Text>
          </LinearGradient>
          <Text style={styles.brandName}>PRANA</Text>
        </View>
      </SafeAreaView>
    </Animated.View>
  );
}

function BounceDot({ delay }: { delay: number }) {
  const y = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    setTimeout(() => {
      Animated.loop(
        Animated.sequence([
          Animated.timing(y, { toValue: -5, duration: 400, useNativeDriver: true }),
          Animated.timing(y, { toValue: 0,  duration: 400, useNativeDriver: true }),
        ])
      ).start();
    }, delay);
  }, []);
  return (
    <Animated.View style={[styles.dot, { transform: [{ translateY: y }] }]} />
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  safe: { flex: 1 },

  orbLeft: {
    position: 'absolute', width: 280, height: 280, borderRadius: 140,
    backgroundColor: colors.indigo, opacity: 0.07,
    top: 40, left: -120,
  },
  orbRight: {
    position: 'absolute', width: 220, height: 220, borderRadius: 110,
    backgroundColor: colors.emerald, opacity: 0.06,
    top: 120, right: -90,
  },

  illustration: {
    width: '100%',
    height: CY * 2 + 60,
    position: 'relative',
  },

  node: {
    position: 'absolute',
    width: 36, height: 36, borderRadius: 11,
    backgroundColor: 'rgba(30,39,71,0.9)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.25)',
    alignItems: 'center', justifyContent: 'center',
  },
  nodeEmoji: { fontSize: 16 },

  vaultWrap: {
    position: 'absolute',
    width: 68, height: 68,
    alignItems: 'center', justifyContent: 'center',
  },
  vaultGlow: {
    position: 'absolute',
    width: 100, height: 100, borderRadius: 50,
    backgroundColor: colors.indigo,
  },
  vaultGrad: {
    width: 68, height: 68, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center',
  },
  vaultEmoji: { fontSize: 30 },

  vaultLabel: {
    position: 'absolute',
    left: 0, right: 0,
    alignItems: 'center',
  },
  vaultLabelText: {
    fontFamily: fonts.mono, fontSize: 9, color: colors.emerald,
    letterSpacing: 2.5,
  },

  copyBlock: {
    flex: 1, paddingHorizontal: 32, justifyContent: 'flex-start', paddingTop: 8,
  },
  tagline: {
    fontFamily: fonts.displayBold, fontSize: 32, color: '#FFFFFF',
    letterSpacing: -0.6, lineHeight: 40, marginBottom: 12,
  },
  taglineAccent: { color: colors.cyan },
  sub: {
    fontSize: 14, color: '#7B8AAB', lineHeight: 22, marginBottom: 24,
  },

  dotsRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  dot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.indigo },

  brand: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 32, paddingBottom: 32,
  },
  brandMark: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  brandIcon: { fontFamily: fonts.displayBold, fontSize: 13, color: '#04261C' },
  brandName: { fontFamily: fonts.displayBold, fontSize: 13, color: '#3D4A6B', letterSpacing: 1.5 },
});
