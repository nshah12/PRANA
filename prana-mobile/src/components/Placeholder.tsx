import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export function Placeholder({ name }: { name: string }) {
  return (
    <View style={styles.container}>
      <Text style={styles.label}>{name}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0B0F1E' },
  label: { color: '#FFFFFF', fontSize: 18, fontWeight: '600' },
});
