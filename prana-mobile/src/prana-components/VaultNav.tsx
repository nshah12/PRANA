// src/components/VaultNav.tsx
//
// Translates .vault-nav / .vault-nav-item / .vault-nav-item.active
//
// CSS used backdrop-filter: blur(20px) on a semi-transparent white background
// for the "floating glass pill" effect. RN has no backdrop-filter; the closest
// equivalent is expo-blur's <BlurView>, which blurs whatever is BEHIND it
// (similar effect, different mechanism -- it's a real-time blur of the
// background content, not a CSS filter on the element itself).

import React from 'react';
import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { colors, fonts, radius } from '../prana-theme/tokens';

const NAV_ITEMS = [
  { key: 'vault', icon: '🗂', label: 'Vault' },
  { key: 'activity', icon: '🕐', label: 'Activity' },
  { key: 'career', icon: '💼', label: 'Career' },
  { key: 'shares', icon: '↗', label: 'Shares' },
  { key: 'settings', icon: '⚙', label: 'Settings' },
] as const;

interface VaultNavProps {
  active: typeof NAV_ITEMS[number]['key'];
  onPress: (key: typeof NAV_ITEMS[number]['key']) => void;
}

export function VaultNav({ active, onPress }: VaultNavProps) {
  return (
    <View style={styles.wrapper}>
      <BlurView intensity={40} tint="light" style={styles.blur}>
        <View style={styles.row}>
          {NAV_ITEMS.map((item) => {
            const isActive = item.key === active;
            return (
              <Pressable
                key={item.key}
                onPress={() => onPress(item.key)}
                style={styles.item}
                // §3 micro-interaction spec: active icon scales to 1.1
                hitSlop={8}
              >
                <Text style={[styles.icon, isActive && styles.iconActive]}>{item.icon}</Text>
                <Text style={[styles.label, isActive && styles.labelActive]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </BlurView>
    </View>
  );
}

const styles = StyleSheet.create({
  // .vault-nav (position: absolute; bottom: 18; left/right: 16)
  wrapper: {
    position: 'absolute',
    bottom: 18,
    left: 16,
    right: 16,
    borderRadius: radius.xl, // 22
    overflow: 'hidden', // clip the BlurView to the rounded corners
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.04)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.18,
    shadowRadius: 16,
    elevation: 8,
  },
  blur: {
    // BlurView intensity=40 + tint="light" approximates
    // rgba(255,255,255,.85) + backdrop-blur(20px)
    paddingVertical: 12,
    // On Android, BlurView support varies by OS version; a solid
    // rgba(255,255,255,0.92) fallback background keeps the pill legible.
    backgroundColor: Platform.OS === 'android' ? 'rgba(255,255,255,0.92)' : 'transparent',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  item: {
    alignItems: 'center',
    gap: 3,
  },
  icon: {
    fontSize: 18,
    // CSS transition: transform .15s -- in RN this scale would be driven by
    // Animated.Value on press; static here since this is a layout PoC.
  },
  iconActive: {
    transform: [{ scale: 1.1 }],
  },
  label: {
    fontFamily: fonts.bodySemiBold,
    fontSize: 10,
    color: colors.ink3,
  },
  labelActive: {
    color: colors.indigo,
  },
});
