/**
 * AuthContext tests — this is the core session state every authenticated
 * screen depends on. The bug worth guarding here: splash.tsx destructures
 * `hasDeviceCredential` from useAuth() (previously cast `as any` to bypass a
 * type error), but AuthContext never actually computed or exposed that field
 * — so the "returning user, trusted device" splash routing branch was dead
 * code in production. Fixed by checking authStore.getDeviceId() at mount
 * time whenever there's no active session.
 */
import React from 'react';
import { render, cleanup, fireEvent } from '@testing-library/react-native';
import { Text, Pressable } from 'react-native';
import { AuthProvider, useAuth } from './AuthContext';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import * as SecureStore from 'expo-secure-store';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/push-notifications', () => ({ refreshPushToken: jest.fn() }));

const TOKEN_KEY = 'prana_access_token';
const mockGet = api.get as jest.Mock;
const mockPost = api.post as jest.Mock;

function Consumer() {
  const { isAuthenticated, hasDeviceCredential, profile, signIn, signOut } = useAuth();
  return (
    <>
      <Text>{`authenticated:${isAuthenticated}`}</Text>
      <Text>{`deviceCredential:${hasDeviceCredential}`}</Text>
      <Text>{`profile:${profile?.name ?? 'none'}`}</Text>
      <Pressable onPress={() => signIn('jwt-new')}><Text>Sign in</Text></Pressable>
      <Pressable onPress={signOut}><Text>Sign out</Text></Pressable>
    </>
  );
}

afterEach(async () => { await cleanup(); });
beforeEach(async () => {
  jest.clearAllMocks();
  authStore.clearToken();
  authStore.clearStepToken();
  authStore.onSignOut = undefined;
  // The expo-secure-store mock is a module-level Map that outlives a single
  // test — clear the device-id slot explicitly so it doesn't leak between tests.
  await SecureStore.deleteItemAsync('prana_device_id');
});

describe('AuthContext', () => {
  it('restores an existing session from storage and loads the profile', async () => {
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockResolvedValue({ name: 'Asha Rao', mobile: '+919000000001', vault_url: '', employer_count: 1, active_since: '2020', has_totp: true });
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    expect(await rtl.findByText('authenticated:true')).toBeTruthy();
    expect(await rtl.findByText('profile:Asha Rao')).toBeTruthy();
  });

  it('stays authenticated even when the profile load fails (non-fatal)', async () => {
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockRejectedValue(new Error('network down'));
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    expect(await rtl.findByText('authenticated:true')).toBeTruthy();
    expect(await rtl.findByText('profile:none')).toBeTruthy();
  });

  it('refreshes the push token on session restore, but not when there is no session', async () => {
    const { refreshPushToken } = require('@/lib/push-notifications');
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockResolvedValue({ name: 'Asha Rao', mobile: '+919000000001', vault_url: '', employer_count: 1, active_since: '2020', has_totp: true });
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    await rtl.findByText('authenticated:true');
    expect(refreshPushToken).toHaveBeenCalledTimes(1);
  });

  it('exposes hasDeviceCredential=true when no session exists but a device id is stored', async () => {
    await SecureStore.setItemAsync('prana_device_id', 'device-1');
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    expect(await rtl.findByText('authenticated:false')).toBeTruthy();
    expect(await rtl.findByText('deviceCredential:true')).toBeTruthy();
  });

  it('exposes hasDeviceCredential=false for a first-time device with no session and no stored device id', async () => {
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    expect(await rtl.findByText('authenticated:false')).toBeTruthy();
    expect(await rtl.findByText('deviceCredential:false')).toBeTruthy();
  });

  it('signIn stores the token, marks authenticated, and loads the profile', async () => {
    mockGet.mockResolvedValue({ name: 'Priya Nair', mobile: '+919000000002', vault_url: '', employer_count: 2, active_since: '2019', has_totp: false });
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    await rtl.findByText('authenticated:false');
    fireEvent.press(await rtl.findByText('Sign in'));
    expect(await rtl.findByText('authenticated:true')).toBeTruthy();
    expect(await rtl.findByText('profile:Priya Nair')).toBeTruthy();
    expect(authStore.getToken()).toBe('jwt-new');
  });

  it('signOut clears the session, resets profile, and best-effort revokes server-side', async () => {
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockResolvedValue({ name: 'Asha Rao', mobile: '+919000000001', vault_url: '', employer_count: 1, active_since: '2020', has_totp: true });
    mockPost.mockResolvedValue({});
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    await rtl.findByText('authenticated:true');
    fireEvent.press(await rtl.findByText('Sign out'));
    expect(await rtl.findByText('authenticated:false')).toBeTruthy();
    expect(await rtl.findByText('profile:none')).toBeTruthy();
    expect(authStore.getToken()).toBeNull();
    expect(mockPost).toHaveBeenCalledWith('/auth/employee/logout');
  });

  it('signOut does not throw when the best-effort logout call fails', async () => {
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockResolvedValue({ name: 'Asha Rao', mobile: '+919000000001', vault_url: '', employer_count: 1, active_since: '2020', has_totp: true });
    mockPost.mockRejectedValue(new Error('offline'));
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    await rtl.findByText('authenticated:true');
    fireEvent.press(await rtl.findByText('Sign out'));
    expect(await rtl.findByText('authenticated:false')).toBeTruthy();
  });

  it('resets to signed-out state when authStore.onSignOut fires externally (e.g. a 401 from api.ts)', async () => {
    await SecureStore.setItemAsync(TOKEN_KEY, 'stored-jwt');
    mockGet.mockResolvedValue({ name: 'Asha Rao', mobile: '+919000000001', vault_url: '', employer_count: 1, active_since: '2020', has_totp: true });
    const rtl = await render(<AuthProvider><Consumer /></AuthProvider>);
    await rtl.findByText('authenticated:true');
    authStore.onSignOut?.();
    expect(await rtl.findByText('authenticated:false')).toBeTruthy();
    expect(await rtl.findByText('profile:none')).toBeTruthy();
  });
});
