/**
 * SharesScreen tests — loading / error / empty / happy states for share links.
 * Uses useShares() (plain useFetch, not react-query) — no QueryClient needed.
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import SharesScreen from './shares';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() } }));
jest.mock('expo-router', () => ({ router: { back: jest.fn(), push: jest.fn() } }));
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
afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

describe('SharesScreen', () => {
  it('shows the loading state (header only) while fetching', async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { getByText, queryByText } = await render(<SharesScreen />);
    expect(getByText('Share links')).toBeTruthy();
    expect(queryByText('Could not load your share links. Try again.')).toBeNull();
  });

  it('shows an error state when the fetch fails (3-state rule)', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    const { findByText } = await render(<SharesScreen />);
    expect(await findByText('Could not load your share links. Try again.')).toBeTruthy();
  });

  it('shows the empty state when there are no shares', async () => {
    mockGet.mockResolvedValue({ shares: [] });
    const { findByText } = await render(<SharesScreen />);
    expect(await findByText('No share links yet')).toBeTruthy();
  });

  it('renders the active/expired/views summary when shares are present', async () => {
    mockGet.mockResolvedValue({
      shares: [
        { token_id: 's1', label: 'For Bank', status: 'ACTIVE',
          expires_at: new Date(Date.now() + 86400000).toISOString(), usage_count: 3, usage_limit: null, created_at: '2024-01-01T00:00:00Z' },
      ],
    });
    const { findByText, getByText } = await render(<SharesScreen />);
    expect(await findByText('Active links')).toBeTruthy();
    expect(getByText('For Bank')).toBeTruthy();
  });
});
