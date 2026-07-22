/**
 * ActivityScreen tests — loading / error / empty / happy states for the
 * pipeline-inbox and document-access sections.
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ActivityScreen from './activity';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn() } }));
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

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('ActivityScreen', () => {
  it('shows the loading state (header only) while fetching', async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { getByText, queryByText } = await render(wrap(<ActivityScreen />));
    expect(getByText('Activity')).toBeTruthy();
    expect(queryByText('Failed to load activity. Tap to retry.')).toBeNull();
  });

  it('shows an error state with a retry button when the query fails', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    const { findByText } = await render(wrap(<ActivityScreen />));
    expect(await findByText('Failed to load activity. Tap to retry.')).toBeTruthy();
    expect(await findByText('Try again')).toBeTruthy();
  });

  it('shows the empty pipeline-inbox state when there are no pushes', async () => {
    mockGet.mockResolvedValue({ access_log: [], pipeline_pushes: [] });
    const { findByText } = await render(wrap(<ActivityScreen />));
    expect(await findByText('No documents yet')).toBeTruthy();
  });

  it('renders a pipeline push card and the access-log section when data is present', async () => {
    mockGet.mockResolvedValue({
      access_log: [{ id: 'a1', action: 'VIEW', doc_title: 'Form 16', occurred_at: '2024-03-01T00:00:00Z' }],
      pipeline_pushes: [{
        id: 'p1', employer: 'TechCorp', doc_count: 2, pushed_at: '2024-03-01T00:00:00Z',
        unread: false, docs: [{ id: 'd1', doc_title: 'Salary Slip', employer: 'TechCorp',
          pushed_at: '2024-03-01T00:00:00Z', status: 'routed', privacy_note: 'ok' }],
      }],
    });
    const { findByText, getByText } = await render(wrap(<ActivityScreen />));
    expect(await findByText('TechCorp')).toBeTruthy();
    expect(getByText('DOCUMENT ACCESS')).toBeTruthy();
    expect(getByText('Form 16')).toBeTruthy();
  });
});
