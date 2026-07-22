/**
 * TotpVerifyScreen tests — auto-submit on 6 digits, step_token requirement,
 * sign-in + routing on success, and attempt-count error mapping.
 *
 * No testID/placeholder on the hidden code input — it's targeted via
 * getByDisplayValue('') (the only empty-value TextInput on this screen).
 * Uses async findBy* throughout (gotcha #3 — this screen fades in via Animated).
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import TotpVerifyScreen from './totp-verify';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
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

const mockPost = api.post as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;
const mockSignIn = jest.fn();
afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReturnValue({ signIn: mockSignIn });
});

describe('TotpVerifyScreen', () => {
  it('redirects to sign-in immediately if there is no step token', async () => {
    authStore.clearStepToken();
    const rtl = await render(<TotpVerifyScreen />);
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '123456');
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in'));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('auto-submits at 6 digits, signs in, and routes to the vault', async () => {
    authStore.setStepToken('step-totp-1');
    mockPost.mockResolvedValue({ access_token: 'jwt-1', is_new_device: false });
    const rtl = await render(<TotpVerifyScreen />);
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '123456');
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/totp',
      { step_token: 'step-totp-1', code: '123456' },
    ));
    await waitFor(() => expect(mockSignIn).toHaveBeenCalledWith('jwt-1'));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(vault)/vault'));
  });

  it('routes to register-device for a new device', async () => {
    authStore.setStepToken('step-totp-2');
    mockPost.mockResolvedValue({ access_token: 'jwt-2', is_new_device: true });
    const rtl = await render(<TotpVerifyScreen />);
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '123456');
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/register-device'));
  });

  it('shows attempts-remaining on a wrong code', async () => {
    authStore.setStepToken('step-totp-3');
    mockPost.mockRejectedValue(Object.assign(new Error('INVALID_TOTP'), {
      status: 401, body: { error: 'INVALID_TOTP' },
    }));
    const rtl = await render(<TotpVerifyScreen />);
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '000000');
    expect(await rtl.findByText('Incorrect code. 4 attempt(s) remaining.')).toBeTruthy();
  });

  it('shows the session-expired message and redirects after a delay', async () => {
    authStore.setStepToken('step-totp-4');
    mockPost.mockRejectedValue(Object.assign(new Error('EXPIRED'), {
      status: 401, body: { error: 'EXPIRED' },
    }));
    const rtl = await render(<TotpVerifyScreen />);
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '000000');
    expect(await rtl.findByText('Your session has expired. Please sign in again.')).toBeTruthy();
    // Real 2s setTimeout in the component before it redirects — wait for it with headroom.
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in'), { timeout: 3000 });
  }, 10000);
});
