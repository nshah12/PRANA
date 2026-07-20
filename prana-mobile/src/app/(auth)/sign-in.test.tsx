/**
 * SignInScreen tests — validation, the identifier+password POST, step-token
 * storage, next-step routing (totp_setup vs totp), and error mapping.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import SignInScreen from './sign-in';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { router } from 'expo-router';

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
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
afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  authStore.clearStepToken();
});

// Screen has continuously-looping Animated.loop() calls (PulsingVault) — use the
// async findBy* queries here (they flush pending act()/animation callbacks via
// retrying), not the sync getBy* variants, to avoid the RTL-v14 empty-render flake.
async function fillAndSubmit(rtl: any, mobile = '9876543210', password = 'secret123') {
  const mobileInput = await rtl.findByPlaceholderText('98765 43210');
  fireEvent.changeText(mobileInput, mobile);
  const pwdInput = await rtl.findByPlaceholderText('Your password');
  fireEvent.changeText(pwdInput, password);
  fireEvent.press(await rtl.findByText('Open my vault  →'));
}

describe('SignInScreen', () => {
  it('renders the headline and CTA', async () => {
    const { getByText } = await render(<SignInScreen />);
    expect(getByText('Welcome back.')).toBeTruthy();
    expect(getByText('Open my vault  →')).toBeTruthy();
  });

  it('shows a validation error and does not call the API with an incomplete form', async () => {
    const { getByText, findByText } = await render(<SignInScreen />);
    fireEvent.press(getByText('Open my vault  →'));
    expect(await findByText('Mobile number is required.')).toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('posts identifier+password, stores the step token, and routes to totp-verify', async () => {
    mockPost.mockResolvedValue({ next: 'totp', step_token: 'step-abc' });
    const rtl = await render(<SignInScreen />);
    await fillAndSubmit(rtl);
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/login',
      { identifier: '+919876543210', password: 'secret123' },
    ));
    expect(authStore.getStepToken()).toBe('step-abc');
    expect(router.push).toHaveBeenCalledWith('/(auth)/totp-verify');
  });

  it('routes to totp-setup when next is totp_setup', async () => {
    mockPost.mockResolvedValue({ next: 'totp_setup', step_token: 'step-xyz' });
    const rtl = await render(<SignInScreen />);
    await fillAndSubmit(rtl);
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/(auth)/totp-setup'));
  });

  it('shows the mapped error message for invalid credentials', async () => {
    mockPost.mockRejectedValue(Object.assign(new Error('INVALID_CREDENTIALS'), {
      status: 401, body: { error: 'INVALID_CREDENTIALS' },
    }));
    const rtl = await render(<SignInScreen />);
    await fillAndSubmit(rtl);
    expect(await rtl.findByText('Incorrect email or password.')).toBeTruthy();
  });

  it('shows the locked-account message for a locked account', async () => {
    mockPost.mockRejectedValue(Object.assign(new Error('ACCOUNT_LOCKED'), {
      status: 403, body: { error: 'ACCOUNT_LOCKED' },
    }));
    const rtl = await render(<SignInScreen />);
    await fillAndSubmit(rtl);
    expect(await rtl.findByText('Account locked. Contact support or wait for auto-unlock.')).toBeTruthy();
  });
});
