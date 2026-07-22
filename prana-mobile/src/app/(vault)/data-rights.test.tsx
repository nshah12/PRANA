/**
 * DataRightsScreen tests — DPDP rights cards, consent banner, the download
 * confirm→mutate→success flow, and the privacy contract (no raw ₹ figures).
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DataRightsScreen from './data-rights';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn() } }));
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
const mockPost = api.post as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function mockEndpoints({ consent = { status: 'ACTIVE', granted_at: '2024-01-01T00:00:00Z' }, docs = { total: 12 } } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/compliance/consent') return Promise.resolve(consent);
    if (url === '/v1/vault/documents?limit=0') return Promise.resolve(docs);
    return Promise.reject(new Error('unexpected url ' + url));
  });
}

describe('DataRightsScreen', () => {
  it('renders the header and all five DPDP right cards', async () => {
    mockEndpoints();
    const { getByText, findByText } = await render(wrap(<DataRightsScreen />));
    expect(getByText('My Data Rights')).toBeTruthy();
    await findByText('What PRANA stores for you');
    for (const title of ['Right to access', 'Right to correction', 'Right to erasure',
      'Right to withdraw consent', 'Right to grievance redressal']) {
      expect(getByText(title)).toBeTruthy();
    }
  });

  it('shows the active-consent banner with the granted date', async () => {
    mockEndpoints({ consent: { status: 'ACTIVE', granted_at: '2024-03-15T00:00:00Z' } });
    const { findByText } = await render(wrap(<DataRightsScreen />));
    expect(await findByText('Consent active')).toBeTruthy();
    expect(await findByText(/15 Mar 2024/)).toBeTruthy();
  });

  it('shows the withdrawn-consent banner with a re-grant button', async () => {
    mockEndpoints({ consent: { status: 'WITHDRAWN', granted_at: null } });
    const { findByText } = await render(wrap(<DataRightsScreen />));
    expect(await findByText('Consent withdrawn')).toBeTruthy();
    expect(await findByText('Re-grant')).toBeTruthy();
  });

  it('walks the download flow: confirm modal → mutate → success modal', async () => {
    mockEndpoints();
    mockPost.mockResolvedValue({});
    const { getByText, findByText } = await render(wrap(<DataRightsScreen />));
    await findByText('What PRANA stores for you');
    fireEvent.press(getByText('Request data download'));
    expect(await findByText('Download your data')).toBeTruthy(); // confirm modal
    fireEvent.press(getByText('Request download'));
    // .mutate() invokes the mutationFn asynchronously — wait for the call rather
    // than asserting synchronously right after the press.
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/vault/compliance/export'));
    expect(await findByText('Request submitted')).toBeTruthy(); // success modal
  });

  it('never renders a raw rupee figure — privacy contract', async () => {
    mockEndpoints();
    const { findByText, toJSON } = await render(wrap(<DataRightsScreen />));
    await findByText('What PRANA stores for you');
    expect(JSON.stringify(toJSON())).not.toMatch(/₹\s*[\d,]+/);
  });
});
