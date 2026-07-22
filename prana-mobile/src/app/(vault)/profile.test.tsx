/**
 * ProfileScreen tests — loading (no profile yet) vs. happy state, driven by
 * AuthContext's `profile` (not react-query — mock the context directly).
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import ProfileScreen from './profile';
import { useAuth } from '@/context/AuthContext';

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

const mockUseAuth = useAuth as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

describe('ProfileScreen', () => {
  it('shows a loading spinner when the profile has not loaded yet', async () => {
    mockUseAuth.mockReturnValue({ profile: null, signOut: jest.fn() });
    const { queryByText } = await render(<ProfileScreen />);
    expect(queryByText('Profile')).toBeNull(); // header only renders once profile exists
  });

  it('renders the profile name, masked mobile, and section headings', async () => {
    mockUseAuth.mockReturnValue({
      profile: {
        name: 'Priya Sharma', mobile: '+919876543210', vault_url: 'prana.in/vault/abc123',
        employer_count: 2, active_since: '2020-01-01', has_totp: true,
      },
      signOut: jest.fn(),
    });
    const { getByText } = await render(<ProfileScreen />);
    expect(getByText('Priya Sharma')).toBeTruthy();
    expect(getByText('PRANA Vault Member')).toBeTruthy();
    expect(getByText('+91 ●●●● ●●●● 3210')).toBeTruthy(); // masked mobile, last 4 digits
    expect(getByText('Vault')).toBeTruthy();
  });

  it('shows the raw vault_url and formatted member-since date', async () => {
    mockUseAuth.mockReturnValue({
      profile: {
        name: 'Priya Sharma', mobile: '+919876543210', vault_url: 'prana.in/vault/abc123',
        employer_count: 2, active_since: '2020-01-15', has_totp: false,
      },
      signOut: jest.fn(),
    });
    const { getByText } = await render(<ProfileScreen />);
    expect(getByText('prana.in/vault/abc123')).toBeTruthy();
    expect(getByText('15 January 2020')).toBeTruthy();
  });
});
