import { Tabs, Redirect } from 'expo-router';
import { View, Text, StyleSheet, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { colors, fonts, radius } from '@/prana-theme/tokens';
import { useAuth } from '@/context/AuthContext';

const NAV_ITEMS = [
  { key: 'vault',    icon: '🗂',  label: 'Vault' },
  { key: 'activity', icon: '🕐',  label: 'Activity' },
  { key: 'career',   icon: '💼',  label: 'Career' },
  { key: 'ask',      icon: '✦',   label: 'Ask' },
] as const;

function TabBar({ state, descriptors, navigation }: any) {
  return (
    <View style={styles.wrapper} pointerEvents="box-none">
      <BlurView intensity={40} tint="light" style={styles.blur}>
        <View style={styles.row}>
          {state.routes.map((route: any, index: number) => {
            const item = NAV_ITEMS[index];
            if (!item) return null; // hidden routes (shares, settings, menu)
            const isFocused = state.index === index;
            const isAsk = item.key === 'ask';
            return (
              <View key={route.key} style={styles.item}>
                <Text
                  style={[styles.icon, isFocused && styles.iconActive, isAsk && styles.iconAsk]}
                  onPress={() => navigation.navigate(route.name)}
                >
                  {item.icon}
                </Text>
                <Text
                  style={[styles.label, isFocused && styles.labelActive]}
                  onPress={() => navigation.navigate(route.name)}
                >
                  {item.label}
                </Text>
              </View>
            );
          })}
        </View>
      </BlurView>
    </View>
  );
}

export default function VaultTabsLayout() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Redirect href="/(auth)/sign-in" />;

  return (
    <Tabs
      tabBar={(props) => <TabBar {...props} />}
      screenOptions={{ headerShown: false }}
    >
      <Tabs.Screen name="vault" />
      <Tabs.Screen name="activity" />
      <Tabs.Screen name="career" />
      <Tabs.Screen name="ask" />
      {/* Hidden from tab bar but still navigable via router.push */}
      <Tabs.Screen name="shares"   options={{ href: null }} />
      <Tabs.Screen name="settings" options={{ href: null }} />
      <Tabs.Screen name="menu"        options={{ href: null }} />
      <Tabs.Screen name="data-rights"  options={{ href: null }} />
      <Tabs.Screen name="profile"      options={{ href: null }} />
      <Tabs.Screen name="vault-health" options={{ href: null }} />
      <Tabs.Screen name="doc-request"  options={{ href: null }} />
      <Tabs.Screen name="privacy"      options={{ href: null }} />
      <Tabs.Screen name="nomination"    options={{ href: null }} />
      <Tabs.Screen name="gamification"  options={{ href: null }} />
      <Tabs.Screen name="alumni"        options={{ href: null }} />
      <Tabs.Screen name="benchmarking"  options={{ href: null }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    position: 'absolute', bottom: 18, left: 16, right: 16,
    borderRadius: radius.xl, overflow: 'hidden',
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.04)',
    shadowColor: '#000', shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.18, shadowRadius: 16, elevation: 8,
  },
  blur: {
    paddingVertical: 12,
    backgroundColor: Platform.OS === 'android' ? 'rgba(255,255,255,0.92)' : 'transparent',
  },
  row: { flexDirection: 'row', justifyContent: 'space-around' },
  item: { alignItems: 'center', gap: 3 },
  icon: { fontSize: 18 },
  iconActive: { transform: [{ scale: 1.1 }] },
  iconAsk: { fontSize: 16, color: colors.indigo, fontWeight: '700' },
  label: { fontFamily: fonts.bodySemiBold, fontSize: 10, color: colors.ink3 },
  labelActive: { color: colors.indigo },
});
