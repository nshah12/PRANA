// App.tsx
//
// Entry point. Loads the three custom font families used throughout the
// prototype (Space Grotesk, Inter, DM Mono) via @expo-google-fonts before
// rendering -- without this step, RN falls back to the system font and
// every `fontFamily: 'SpaceGrotesk_700Bold'` etc. reference in tokens.ts
// silently no-ops.

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { SpaceGrotesk_600SemiBold, SpaceGrotesk_700Bold } from '@expo-google-fonts/space-grotesk';
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
} from '@expo-google-fonts/inter';
import { DMMono_500Medium } from '@expo-google-fonts/dm-mono';
import { View, ActivityIndicator } from 'react-native';

import { VaultHomeScreen } from './src/screens/VaultHomeScreen';
import { colors } from './src/theme/tokens';

export default function App() {
  const [fontsLoaded] = useFonts({
    SpaceGrotesk_600SemiBold,
    SpaceGrotesk_700Bold,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    DMMono_500Medium,
  });

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface }}>
        <ActivityIndicator color={colors.indigo} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <VaultHomeScreen />
    </SafeAreaProvider>
  );
}
