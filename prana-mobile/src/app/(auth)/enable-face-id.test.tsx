/**
 * EnableFaceIdScreen tests — the real bug this screen had was calling a
 * nonexistent endpoint (/auth/employee/device/enroll-biometric) with a
 * step_token, and separately treating authStore.getDeviceId() (async) as if
 * it were synchronous. The fixed contract is POST
 * /auth/employee/device/{device_id}/biometric with an empty body, only after
 * awaiting a real device id. This screen also loops an Animated ring while
 * scanning, so every query uses async findBy* per the RTL v14 gotcha #3
 * mitigation documented in CLAUDE.md.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import EnableFaceIdScreen from './enable-face-id';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { router } from 'expo-router';
import * as LocalAuthentication from 'expo-local-authentication';

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('expo-local-authentication', () => ({
  authenticateAsync: jest.fn(),
  supportedAuthenticationTypesAsync: jest.fn().mockResolvedValue([]),
  AuthenticationType: { FACIAL_RECOGNITION: 1, FINGERPRINT: 2 },
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
const mockAuthenticate = LocalAuthentication.authenticateAsync as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(authStore, 'getDeviceId').mockResolvedValue('device-xyz');
});

describe('EnableFaceIdScreen', () => {
  it('renders the enable CTA and skip option', async () => {
    const rtl = await render(<EnableFaceIdScreen />);
    expect(await rtl.findByText(/Enable Face ID/)).toBeTruthy();
    expect(await rtl.findByText('Skip for now — I\'ll enable it later')).toBeTruthy();
  });

  it('enrolls with the device-id path param and an empty body, then navigates to consent', async () => {
    mockAuthenticate.mockResolvedValue({ success: true });
    mockPost.mockResolvedValue({ enrolled: true });
    const rtl = await render(<EnableFaceIdScreen />);
    fireEvent.press(await rtl.findByText(/Enable Face ID/));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/device/device-xyz/biometric',
      {},
    ));
  });

  it('does not call the API and shows an error when no device id is stored', async () => {
    jest.spyOn(authStore, 'getDeviceId').mockResolvedValue(null);
    mockAuthenticate.mockResolvedValue({ success: true });
    const rtl = await render(<EnableFaceIdScreen />);
    fireEvent.press(await rtl.findByText(/Enable Face ID/));
    expect(await rtl.findByText('Could not complete enrollment. You can enable this later in Settings.')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('skips straight to consent without enrolling', async () => {
    const rtl = await render(<EnableFaceIdScreen />);
    fireEvent.press(await rtl.findByText('Skip for now — I\'ll enable it later'));
    expect(router.replace).toHaveBeenCalledWith('/(auth)/consent');
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('shows an error when the device fails local biometric authentication', async () => {
    mockAuthenticate.mockResolvedValue({ success: false, error: 'not_enrolled' });
    const rtl = await render(<EnableFaceIdScreen />);
    fireEvent.press(await rtl.findByText(/Enable Face ID/));
    expect(await rtl.findByText('Biometric check failed. Try again or sign in another way.')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
