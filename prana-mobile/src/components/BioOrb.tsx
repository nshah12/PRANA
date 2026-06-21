import React, { useEffect, useRef } from 'react';
import { View, Text, Animated, Easing, StyleSheet } from 'react-native';
import { colors } from '@/prana-theme/tokens';

export function BioOrb() {
  const spin = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.timing(spin, { toValue: 1, duration: 2400, easing: Easing.linear, useNativeDriver: true })
    ).start();
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1200, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1200, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] });

  return (
    <View style={styles.wrap}>
      <Animated.View style={[styles.orb, { transform: [{ scale }] }]}>
        <Text style={styles.icon}>👤</Text>
        {/* Spinning ring */}
        <Animated.View style={[styles.ring, { transform: [{ rotate }] }]} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center', paddingVertical: 32 },
  orb: {
    width: 120, height: 120, borderRadius: 36,
    backgroundColor: 'rgba(99,102,241,0.15)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center', justifyContent: 'center',
  },
  icon: { fontSize: 48 },
  ring: {
    position: 'absolute', inset: -8,
    width: 136, height: 136, borderRadius: 44,
    borderWidth: 2.5, borderColor: 'transparent',
    borderTopColor: colors.cyan, borderLeftColor: colors.cyan,
  },
});
