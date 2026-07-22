/**
 * BiometricUnlockScreen tests — this screen is reached straight from splash.tsx
 * with no prior password step, so there is no step_token available. The fixed
 * contract points at the real /biometric endpoint (which does require a
 * step_token) but the screen can only call it when both a stored device id and
 * a step token are present; otherwise it must fail closed with an error rather
 * than silently sending a bad request (the original bug: an un-awaited
 * getDeviceId() promise was always truthy, so the 'unknown' fallback never
 * actually ran). RecognitionOrb loops an Animated pulse in 'waiting' state, so
 * every query uses async findBy* per RTL v14 gotcha #3.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import BiometricUnlockScreen from './biometric-unlock';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';
import * as LocalAuthentication from 'expo-local-authentication';

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('expo-local-authentication', () => ({
  authenticateAsync: jest.fn(),
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
const mockUseAuth = useAuth as jest.Mock;
const mockAuthenticate = LocalAuthentication.authenticateAsync as jest.Mock;
const mockSignIn = jest.fn();
afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReturnValue({ signIn: mockSignIn, profile: { name: 'Asha Rao' } });
  jest.spyOn(authStore, 'getDeviceId').mockResolvedValue('device-xyz');
  authStore.setStepToken('step-unlock-1');
});

describe('BiometricUnlockScreen', () => {
  it('greets the user by first name while waiting', async () => {
    const rtl = await render(<BiometricUnlockScreen />);
    expect(await rtl.findByText('Welcome back, Asha.')).toBeTruthy();
  });

  it('exchanges a successful local scan for an access token via the real step-token contract', async () => {
    mockAuthenticate.mockResolvedValue({ success: true });
    mockPost.mockResolvedValue({ access_token: 'jwt-unlock-1' });
    const rtl = await render(<BiometricUnlockScreen />);
    fireEvent.press(await rtl.findByText('Unlock vault'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/biometric',
      { step_token: 'step-unlock-1', device_id: 'device-xyz' },
    ));
    expect(mockSignIn).toHaveBeenCalledWith('jwt-unlock-1');
  });

  it('fails closed without calling the API when there is no device id', async () => {
    jest.spyOn(authStore, 'getDeviceId').mockResolvedValue(null);
    mockAuthenticate.mockResolvedValue({ success: true });
    const rtl = await render(<BiometricUnlockScreen />);
    fireEvent.press(await rtl.findByText('Unlock vault'));
    expect(await rtl.findByText('Try again')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('fails closed without calling the API when there is no step token', async () => {
    authStore.clearStepToken();
    mockAuthenticate.mockResolvedValue({ success: true });
    const rtl = await render(<BiometricUnlockScreen />);
    fireEvent.press(await rtl.findByText('Unlock vault'));
    expect(await rtl.findByText('Try again')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('lets the user cancel back to waiting without an error', async () => {
    mockAuthenticate.mockResolvedValue({ success: false, error: 'user_cancel' });
    const rtl = await render(<BiometricUnlockScreen />);
    fireEvent.press(await rtl.findByText('Unlock vault'));
    await waitFor(() => expect(mockAuthenticate).toHaveBeenCalled());
    expect(await rtl.findByText('Unlock vault')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('routes to sign-in via the alternate sign-in link', async () => {
    const rtl = await render(<BiometricUnlockScreen />);
    fireEvent.press(await rtl.findByText('Sign in another way'));
    expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
  });
});
