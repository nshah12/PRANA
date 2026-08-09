/**
 * RegisterDeviceScreen tests — this screen is Bearer-authenticated (not step-token
 * based, unlike most of the auth flow), so the key contract to verify is that it
 * reads authStore.getToken() as its guard, posts the uppercase platform + public_key
 * body the backend's DeviceRegisterIn model actually expects, and stores the
 * returned device_id for later screens (enable-face-id) to use.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import RegisterDeviceScreen from './register-device';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { router } from 'expo-router';
import * as SecureStore from 'expo-secure-store';

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('expo-device', () => ({ modelName: 'Pixel 9' }));
// Permission denial resolves quickly and deterministically — matches how
// a real device without push permission behaves (registration still
// succeeds, just without a push_token in the body).
jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: 'denied' }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: 'denied' }),
  getExpoPushTokenAsync: jest.fn(),
}));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockPost = api.post as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  authStore.setToken('access-token-1');
  // clearAllMocks() clears call history but not a mockResolvedValue's
  // implementation — reset the permission default explicitly each test so
  // the "granted" test below can't bleed into later tests.
  const Notifications = require('expo-notifications');
  Notifications.getPermissionsAsync.mockResolvedValue({ status: 'denied' });
  Notifications.requestPermissionsAsync.mockResolvedValue({ status: 'denied' });
});

describe('RegisterDeviceScreen', () => {
  it('renders the step copy and device card', async () => {
    const rtl = await render(<RegisterDeviceScreen />);
    expect(await rtl.findByText(/Pixel 9/)).toBeTruthy();
  });

  it('redirects to sign-in instead of calling the API when there is no access token', async () => {
    authStore.clearToken();
    const rtl = await render(<RegisterDeviceScreen />);
    fireEvent.press(await rtl.findByText('Trust this device →'));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in'));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('registers the device with an uppercase platform and a public_key, then stores device_id', async () => {
    mockPost.mockResolvedValue({ device_id: 'device-abc' });
    const setItemSpy = jest.spyOn(SecureStore, 'setItemAsync').mockResolvedValue();
    const rtl = await render(<RegisterDeviceScreen />);
    fireEvent.press(await rtl.findByText('Trust this device →'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/device/register',
      expect.objectContaining({ platform: expect.stringMatching(/^(ANDROID|IOS)$/), public_key: expect.any(String) }),
    ));
    await waitFor(() => expect(setItemSpy).toHaveBeenCalledWith('prana_device_id', 'device-abc'));
    expect(await rtl.findByText('Device trusted ✓')).toBeTruthy();
  });

  it('includes push_token in the register body when permission is granted', async () => {
    const Notifications = require('expo-notifications');
    Notifications.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    Notifications.getExpoPushTokenAsync.mockResolvedValue({ data: 'ExponentPushToken[abc]' });
    mockPost.mockResolvedValue({ device_id: 'device-abc' });

    const rtl = await render(<RegisterDeviceScreen />);
    fireEvent.press(await rtl.findByText('Trust this device →'));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/device/register',
      expect.objectContaining({ push_token: 'ExponentPushToken[abc]' }),
    ));
  });

  it('registers without a push_token when permission is denied — never blocks registration', async () => {
    mockPost.mockResolvedValue({ device_id: 'device-abc' });
    const rtl = await render(<RegisterDeviceScreen />);
    fireEvent.press(await rtl.findByText('Trust this device →'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const body = mockPost.mock.calls[0][1];
    expect(body.push_token).toBeUndefined();
  });

  it('shows the device-limit error message on DEVICE_LIMIT_REACHED', async () => {
    mockPost.mockRejectedValue(Object.assign(new Error('DEVICE_LIMIT_REACHED'), {
      status: 400,
      body: { error: 'DEVICE_LIMIT_REACHED' },
    }));
    const rtl = await render(<RegisterDeviceScreen />);
    fireEvent.press(await rtl.findByText('Trust this device →'));
    expect(await rtl.findByText(/device limit/i)).toBeTruthy();
  });
});
