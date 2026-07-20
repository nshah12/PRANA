/**
 * Tests for the in-memory + SecureStore token store.
 * SecureStore is mocked in jest.setup.js (in-memory stub).
 */
import * as SecureStore from 'expo-secure-store';
import { authStore } from './auth-store';

const TOKEN_KEY = 'prana_access_token';

beforeEach(() => {
  authStore.clearToken();
  authStore.clearStepToken();
  authStore.onSignOut = undefined;
  jest.clearAllMocks();
});

describe('authStore — access token', () => {
  it('holds the token in memory after setToken', () => {
    expect(authStore.getToken()).toBeNull();
    authStore.setToken('tok-123');
    expect(authStore.getToken()).toBe('tok-123');
  });

  it('persists the token to SecureStore on setToken', () => {
    authStore.setToken('tok-abc');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok-abc');
  });

  it('clearToken wipes memory and deletes from SecureStore', () => {
    authStore.setToken('tok-xyz');
    authStore.clearToken();
    expect(authStore.getToken()).toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
  });

  it('loadFromStorage restores a persisted token into memory', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('restored-tok');
    const restored = await authStore.loadFromStorage();
    expect(restored).toBe('restored-tok');
    expect(authStore.getToken()).toBe('restored-tok');
  });

  it('loadFromStorage leaves the token null when nothing is stored', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce(null);
    const restored = await authStore.loadFromStorage();
    expect(restored).toBeNull();
    expect(authStore.getToken()).toBeNull();
  });
});

describe('authStore — transient step token & pending mobile', () => {
  it('step token is settable/clearable and never persisted to SecureStore', () => {
    authStore.setStepToken('step-1');
    expect(authStore.getStepToken()).toBe('step-1');
    authStore.clearStepToken();
    expect(authStore.getStepToken()).toBeNull();
    expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
  });

  it('pending mobile round-trips', () => {
    authStore.setPendingMobile('+919000000001');
    expect(authStore.getPendingMobile()).toBe('+919000000001');
  });
});

describe('authStore — device id', () => {
  it('reads/writes the device id via SecureStore', async () => {
    await authStore.setDeviceId('dev-1');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('prana_device_id', 'dev-1');
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('dev-1');
    expect(await authStore.getDeviceId()).toBe('dev-1');
  });
});
