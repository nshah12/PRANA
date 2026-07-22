/**
 * SplashScreen tests — the only real logic here is the routing decision made
 * 4s after mount: authenticated -> vault, device-credentialed but not signed
 * in -> biometric-unlock, otherwise -> sign-in. Everything else is animation.
 * Real timers are used (matching the totp-verify.test.tsx precedent in this
 * codebase) with a generous waitFor timeout and a bumped test timeout.
 */
import React from 'react';
import { render, cleanup, waitFor } from '@testing-library/react-native';
import SplashScreen from './splash';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockUseAuth = useAuth as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => { jest.clearAllMocks(); });

describe('SplashScreen', () => {
  it('routes to the vault when already authenticated', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, hasDeviceCredential: false });
    await render(<SplashScreen />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(vault)/vault'), { timeout: 5000 });
  }, 10000);

  it('routes to biometric-unlock for a trusted device with no active session', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, hasDeviceCredential: true });
    await render(<SplashScreen />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/biometric-unlock'), { timeout: 5000 });
  }, 10000);

  it('routes to sign-in for a first-time or fully signed-out user', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, hasDeviceCredential: false });
    await render(<SplashScreen />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in'), { timeout: 5000 });
  }, 10000);
});
