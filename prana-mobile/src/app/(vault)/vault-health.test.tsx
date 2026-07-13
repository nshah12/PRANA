/**
 * VaultHealthScreen tests — loading / error / happy states, gap surfacing,
 * and the privacy contract (no raw ₹ figures — score + insights only).
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import VaultHealthScreen from './vault-health';
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

function mockEndpoints({ health, reject = false }: any) {
  const profile = { employers: [{ tenant_name: 'TechCorp' }], employer_count: 1 };
  const docs = { documents: [], count: 5 };
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/health') return reject ? Promise.reject(new Error('boom')) : Promise.resolve(health);
    if (url === '/v1/vault/profile') return Promise.resolve(profile);
    if (url === '/v1/vault/documents') return Promise.resolve(docs);
    return Promise.reject(new Error('unexpected url ' + url));
  });
}

const HEALTH = {
  overall_score: 85,
  gap_count: 1,
  gap_detail: [{ doc_type: 'FORM_16', employer: 'TechCorp', severity: 'HIGH' }],
};

describe('VaultHealthScreen', () => {
  it('shows the loading state (header only) while fetching', async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { getByText, queryByText } = await render(wrap(<VaultHealthScreen />));
    expect(getByText('Vault Health')).toBeTruthy();
    expect(queryByText('COMPLETENESS BREAKDOWN')).toBeNull();
    expect(queryByText('Could not load health data. Try again later.')).toBeNull();
  });

  it('shows an error state when the health query fails', async () => {
    mockEndpoints({ reject: true });
    const { findByText } = await render(wrap(<VaultHealthScreen />));
    expect(await findByText('Could not load health data. Try again later.')).toBeTruthy();
  });

  it('renders the score, breakdown and gaps when data is present', async () => {
    mockEndpoints({ health: HEALTH });
    const { findByText, getByText } = await render(wrap(<VaultHealthScreen />));
    expect(await findByText('Vault Health Score')).toBeTruthy();
    expect(getByText('85')).toBeTruthy();                    // score
    expect(getByText('COMPLETENESS BREAKDOWN')).toBeTruthy();
    expect(getByText('FORM 16')).toBeTruthy();               // surfaced gap
  });

  it('never renders a raw rupee figure — privacy contract', async () => {
    mockEndpoints({ health: HEALTH });
    const { findByText, toJSON } = await render(wrap(<VaultHealthScreen />));
    await findByText('Vault Health Score');
    expect(JSON.stringify(toJSON())).not.toMatch(/₹\s*[\d,]+/);
  });
});
