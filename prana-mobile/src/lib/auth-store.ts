/**
 * In-memory token store with SecureStore persistence.
 * Token lives in-memory for the session; restored from SecureStore on app launch.
 * onSignOut callback is set by AuthContext to trigger navigation.
 */

import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'prana_access_token';
const STEP_TOKEN_KEY = 'prana_step_token';

let _token: string | null = null;
let _stepToken: string | null = null;
let _pendingMobile: string | null = null;

export const authStore = {
  onSignOut: undefined as (() => void) | undefined,

  getToken(): string | null {
    return _token;
  },

  setToken(token: string) {
    _token = token;
    SecureStore.setItemAsync(TOKEN_KEY, token).catch(() => {});
  },

  clearToken() {
    _token = null;
    SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => {});
  },

  async loadFromStorage(): Promise<string | null> {
    const stored = await SecureStore.getItemAsync(TOKEN_KEY);
    if (stored) _token = stored;
    return stored;
  },

  // Step token is transient between login steps — not persisted
  getStepToken(): string | null { return _stepToken; },
  setStepToken(t: string)       { _stepToken = t; },
  clearStepToken()              { _stepToken = null; },

  // Pending mobile: set at sign-in, cleared after OTP verify
  getPendingMobile(): string | null { return _pendingMobile; },
  setPendingMobile(m: string)       { _pendingMobile = m; },

  // Device ID: stable per-install identifier stored in SecureStore
  async getDeviceId(): Promise<string | null> {
    return SecureStore.getItemAsync('prana_device_id');
  },
  async setDeviceId(id: string): Promise<void> {
    await SecureStore.setItemAsync('prana_device_id', id);
  },
};
