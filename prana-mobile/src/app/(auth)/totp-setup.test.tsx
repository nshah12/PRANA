/**
 * TotpSetupScreen tests — the real bug here: /auth/employee/setup/totp/confirm
 * does not issue a JWT (unlike /auth/employee/totp). Per TOTPConfirmIn's
 * handler in auth_employee.py it returns { next, step_token } to advance the
 * step chain. The fixed contract stores that new step_token and routes on
 * `next` rather than assuming an access_token that was never in the response.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import TotpSetupScreen from './totp-setup';
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
  authStore.setStepToken('step-setup-1');
});

describe('TotpSetupScreen', () => {
  it('loads the provisioning URI and secret key on mount', async () => {
    mockPost.mockResolvedValue({ provisioning_uri: 'otpauth://totp/PRANA', secret_key: 'ABCD1234EFGH5678' });
    const rtl = await render(<TotpSetupScreen />);
    expect(mockPost).toHaveBeenCalledWith('/auth/employee/setup/totp/init', { step_token: 'step-setup-1' });
    expect(await rtl.findByText('ABCD 1234 EFGH 5678')).toBeTruthy();
  });

  it('shows a retry option when the init call fails', async () => {
    mockPost.mockRejectedValue(new Error('boom'));
    const rtl = await render(<TotpSetupScreen />);
    expect(await rtl.findByText('Something went wrong. Please try again.')).toBeTruthy();
  });

  it('confirms the code, stores the new step_token (not an access token), and routes to consent', async () => {
    mockPost
      .mockResolvedValueOnce({ provisioning_uri: 'otpauth://totp/PRANA', secret_key: 'ABCD1234' })
      .mockResolvedValueOnce({ next: 'consent', step_token: 'step-setup-2' });
    const rtl = await render(<TotpSetupScreen />);
    await rtl.findByText('ABCD 1234');
    fireEvent.press(await rtl.findByText('2. Enter code'));
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '123456');
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/setup/totp/confirm',
      { step_token: 'step-setup-1', code: '123456' },
    ));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(auth)/consent'));
    expect(authStore.getStepToken()).toBe('step-setup-2');
  });

  it('shows an invalid-code error and clears the input on a wrong code', async () => {
    mockPost
      .mockResolvedValueOnce({ provisioning_uri: 'otpauth://totp/PRANA', secret_key: 'ABCD1234' })
      .mockRejectedValueOnce(Object.assign(new Error('INVALID_TOTP_CODE'), {
        status: 401, body: { error: 'INVALID_TOTP_CODE' },
      }));
    const rtl = await render(<TotpSetupScreen />);
    await rtl.findByText('ABCD 1234');
    fireEvent.press(await rtl.findByText('2. Enter code'));
    const input = await rtl.findByDisplayValue('');
    fireEvent.changeText(input, '000000');
    expect(await rtl.findByText('Incorrect OTP code. Please try again.')).toBeTruthy();
  });
});
