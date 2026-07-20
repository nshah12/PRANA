/**
 * BenchmarkingScreen tests — consent gating, opted-out / building / has-data states,
 * and the privacy contract (no raw ₹ figures — bands only).
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BenchmarkingScreen from './benchmarking';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn() } }));
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

function mockEndpoints({ consent, position }: { consent: any; position?: any }) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/benchmarking/consent') return Promise.resolve(consent);
    if (url === '/v1/benchmarking/my-position') return Promise.resolve(position ?? { items: [] });
    return Promise.reject(new Error('unexpected url ' + url));
  });
}

describe('BenchmarkingScreen', () => {
  it('shows the opted-out state when the employee has not consented', async () => {
    mockEndpoints({ consent: { peer_benchmark_consent: false } });
    const { getByText, findByText } = await render(wrap(<BenchmarkingScreen />));
    expect(getByText('Comp Benchmarking')).toBeTruthy();          // header always
    expect(await findByText('See where you stand')).toBeTruthy(); // opted-out empty state
  });

  it('shows the "building" state when opted in but no cohort data yet', async () => {
    mockEndpoints({ consent: { peer_benchmark_consent: true }, position: { items: [] } });
    const { findByText } = await render(wrap(<BenchmarkingScreen />));
    expect(await findByText('YOUR MARKET POSITION')).toBeTruthy();
    expect(await findByText('Building your benchmark')).toBeTruthy();
  });

  it('renders a percentile band (not a raw figure) when cohort data is present', async () => {
    mockEndpoints({
      consent: { peer_benchmark_consent: true },
      position: { items: [
        { cohort_key: 'GRADE_L5', percentile_band: 'P50-P75', label_text: 'Mid of your band',
          data_freshness: 'today', suppressed: false },
      ] },
    });
    const { findByText } = await render(wrap(<BenchmarkingScreen />));
    expect(await findByText('P50-P75')).toBeTruthy();
    expect(await findByText('Mid of your band')).toBeTruthy();
  });

  it('never renders a raw rupee figure — privacy contract', async () => {
    mockEndpoints({
      consent: { peer_benchmark_consent: true },
      position: { items: [
        { cohort_key: 'GRADE_L5', percentile_band: 'P50-P75', label_text: 'Mid of your band',
          data_freshness: 'today', suppressed: false },
      ] },
    });
    const { findByText, toJSON } = await render(wrap(<BenchmarkingScreen />));
    await findByText('P50-P75');
    expect(JSON.stringify(toJSON())).not.toMatch(/₹\s*[\d,]+/);
  });
});
