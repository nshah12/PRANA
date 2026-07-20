/**
 * ConsentScreen tests — the DPDP consent gate is the final setup step: accepting
 * must POST the correct endpoint, store the returned access token via signIn(),
 * and only then navigate. The CTA must stay disabled until the checkbox is checked.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import ConsentScreen from './consent';
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
  authStore.setStepToken('step-consent-1');
});

describe('ConsentScreen', () => {
  it('renders the heading and checkbox label', async () => {
    const rtl = await render(<ConsentScreen />);
    expect(await rtl.findByText('Before we begin')).toBeTruthy();
    expect(rtl.getByText(/I have read and understood/)).toBeTruthy();
  });

  it('does not submit when the checkbox is unchecked', async () => {
    const rtl = await render(<ConsentScreen />);
    fireEvent.press(await rtl.findByText('I consent — Open my vault →'));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('posts the step token to /auth/employee/setup/consent, signs in, and opens the vault', async () => {
    mockPost.mockResolvedValue({ access_token: 'jwt-consent-1' });
    const rtl = await render(<ConsentScreen />);
    fireEvent.press(await rtl.findByText(/I have read and understood/));
    await rtl.findByText('✓'); // wait for the checkbox `agreed` state to commit before pressing the CTA
    fireEvent.press(rtl.getByText('I consent — Open my vault →'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/auth/employee/setup/consent',
      expect.objectContaining({ step_token: 'step-consent-1' }),
    ));
    expect(mockSignIn).toHaveBeenCalledWith('jwt-consent-1');
    expect(router.replace).toHaveBeenCalledWith('/(vault)/vault');
  });

  it('shows an error and does not sign in when the request fails', async () => {
    mockPost.mockRejectedValue(new Error('boom'));
    const rtl = await render(<ConsentScreen />);
    fireEvent.press(await rtl.findByText(/I have read and understood/));
    await rtl.findByText('✓'); // wait for the checkbox `agreed` state to commit before pressing the CTA
    fireEvent.press(rtl.getByText('I consent — Open my vault →'));
    expect(await rtl.findByText('Could not record your consent. Check your connection and try again.')).toBeTruthy();
    expect(mockSignIn).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
  });
});
