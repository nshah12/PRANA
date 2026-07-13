/**
 * CareerScreen tests — loading / error / empty / happy states, and the
 * privacy contract (growth index only — no raw ₹ salary figures).
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CareerScreen from './career';
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

const CAREER_DATA = {
  growth_data: [
    { period: '2022-01', index: 100, employer_id: 'e1', employer_name: 'TechCorp', doc_type: 'SALARY_SLIP', note: '' },
    { period: '2023-01', index: 118, employer_id: 'e1', employer_name: 'TechCorp', doc_type: 'SALARY_SLIP', note: '' },
  ],
  employers: [{ id: 'e1', name: 'TechCorp', role: 'Engineer', from: '2022-01-01', to: null }],
  events: [{ id: 'ev1', type: 'promotion', label: 'Promoted to Senior Engineer', employer_id: 'e1', at: '2023-06-01' }],
};

describe('CareerScreen', () => {
  it('shows the loading state (header only) while fetching', async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { getByText, queryByText } = await render(wrap(<CareerScreen />));
    expect(getByText('Career')).toBeTruthy();
    expect(queryByText('Could not load career data. Try again later.')).toBeNull();
  });

  it('shows an error state when the query fails', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    const { findByText } = await render(wrap(<CareerScreen />));
    expect(await findByText('Could not load career data. Try again later.')).toBeTruthy();
  });

  it('shows the empty-chart hint when there is no growth data', async () => {
    mockGet.mockResolvedValue({ growth_data: [], employers: [], events: [] });
    const { findByText } = await render(wrap(<CareerScreen />));
    expect(await findByText('Upload salary slips or increment letters to see your growth chart.')).toBeTruthy();
  });

  it('renders employer, growth summary, and career events when data is present', async () => {
    mockGet.mockResolvedValue(CAREER_DATA);
    const { findByText, getByText } = await render(wrap(<CareerScreen />));
    expect(await findByText('SALARY GROWTH INDEX')).toBeTruthy();
    expect(getByText('Promoted to Senior Engineer')).toBeTruthy();
    expect(getByText('EMPLOYERS')).toBeTruthy();
  });

  it('never renders a raw rupee figure — privacy contract', async () => {
    mockGet.mockResolvedValue(CAREER_DATA);
    const { findByText, toJSON } = await render(wrap(<CareerScreen />));
    await findByText('SALARY GROWTH INDEX');
    expect(JSON.stringify(toJSON())).not.toMatch(/₹\s*[\d,]+/);
  });
});
