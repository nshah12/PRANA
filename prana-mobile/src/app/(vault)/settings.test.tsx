/**
 * SettingsScreen tests — trusted-devices empty/happy states and the sign-out action.
 * Uses raw useEffect + api.get (not react-query) and useAuth for signOut.
 */
import React from 'react';
import { render, cleanup, fireEvent } from '@testing-library/react-native';
import SettingsScreen from './settings';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), delete: jest.fn() } }));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({ router: { back: jest.fn(), push: jest.fn(), replace: jest.fn() } }));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockGet = api.get as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

describe('SettingsScreen', () => {
  it('shows the empty-devices copy when there are no trusted devices', async () => {
    mockGet.mockResolvedValue({ devices: [] });
    mockUseAuth.mockReturnValue({ signOut: jest.fn() });
    const { findByText } = await render(<SettingsScreen />);
    expect(await findByText('No trusted devices yet')).toBeTruthy();
  });

  it('renders a device row with a Remove button for non-current devices', async () => {
    mockGet.mockResolvedValue({
      devices: [
        { id: 'd1', name: 'iPhone 15', platform: 'ios', is_current: false, trusted_at: '2024-01-01T00:00:00Z' },
        { id: 'd2', name: 'This Pixel', platform: 'android', is_current: true, trusted_at: '2024-01-01T00:00:00Z' },
      ],
    });
    mockUseAuth.mockReturnValue({ signOut: jest.fn() });
    const { findByText, getByText } = await render(<SettingsScreen />);
    expect(await findByText('iPhone 15')).toBeTruthy();
    expect(getByText('Remove')).toBeTruthy();
    expect(getByText('Current')).toBeTruthy();
  });

  it('signs out and navigates to sign-in when Sign out is pressed', async () => {
    mockGet.mockResolvedValue({ devices: [] });
    const signOut = jest.fn();
    mockUseAuth.mockReturnValue({ signOut });
    const { findByText } = await render(<SettingsScreen />);
    fireEvent.press(await findByText('Sign out'));
    expect(signOut).toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
  });
});
