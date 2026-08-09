/**
 * Expo push token acquisition — used once at device registration
 * (register-device.tsx) and again on every authenticated app foreground
 * (to catch a rotated token; POST /auth/employee/device/register is
 * idempotent on public_key, so re-sending is a safe no-op refresh).
 *
 * Never blocks registration: permission denial or any native error resolves
 * to null rather than throwing — a device without push is still a valid,
 * fully-functional device.
 */
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';

export async function getExpoPushTokenOrNull(): Promise<string | null> {
  if (Platform.OS === 'web') return null;

  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;
    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') return null;

    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const { data } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    return data ?? null;
  } catch {
    return null;
  }
}

/**
 * Fire-and-forget refresh, called on every authenticated app launch
 * (AuthContext). Expo tokens can rotate between sessions — re-sending with
 * the SAME persisted public_key is an idempotent no-op if unchanged (the
 * endpoint's ON CONFLICT (public_key) upsert), and picks up a rotated token
 * if it changed. Silently no-ops if this device was never registered
 * (no persisted public_key) or push permission isn't granted — never
 * throws, never blocks app startup.
 */
export async function refreshPushToken(): Promise<void> {
  try {
    const publicKey = await authStore.getPublicKey();
    if (!publicKey) return;
    const pushToken = await getExpoPushTokenOrNull();
    if (!pushToken) return;
    await api.post('/auth/employee/device/register', {
      platform: Platform.OS === 'ios' ? 'IOS' : 'ANDROID',
      public_key: publicKey,
      push_token: pushToken,
    });
  } catch {
    // Non-fatal — a stale push token just means push notifications lag
    // until the next successful refresh.
  }
}
