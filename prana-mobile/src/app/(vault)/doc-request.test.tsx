/**
 * DocRequestScreen tests — loading / error / empty / happy states.
 * Screen-test template for prana-mobile: QueryClient wrapper + mocked api,
 * expo-router, and safe-area-context. Render-only (no fireEvent) to stay clear
 * of the RTL-v14 multi-render flake documented in CLAUDE.md.
 */
import React from 'react';
import { render, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DocRequestScreen from './doc-request';
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

afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

// api.get is called for both /v1/vault/requests and /v1/vault/profile.
function mockEndpoints({ requests, profile = { employers: [] }, reject = false }: any) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/requests') {
      return reject ? Promise.reject(new Error('boom')) : Promise.resolve(requests);
    }
    if (url === '/v1/vault/profile') return Promise.resolve(profile);
    return Promise.reject(new Error('unexpected url ' + url));
  });
}

describe('DocRequestScreen', () => {
  it('shows the loading state (header only, no resolved states) while fetching', async () => {
    mockGet.mockReturnValue(new Promise(() => {})); // never resolves → stuck loading
    const { getByText, queryByText } = await render(wrap(<DocRequestScreen />));
    expect(getByText('Document Requests')).toBeTruthy();          // header always renders
    expect(queryByText('No requests yet')).toBeNull();            // not the empty state
    expect(queryByText('Could not load requests.')).toBeNull();   // not the error state
  });

  it('shows an error state when the requests query fails', async () => {
    mockEndpoints({ reject: true });
    const { findByText } = await render(wrap(<DocRequestScreen />));
    expect(await findByText('Could not load requests.')).toBeTruthy();
  });

  it('shows an empty state when there are no requests', async () => {
    mockEndpoints({ requests: { items: [], total: 0 } });
    const { findByText } = await render(wrap(<DocRequestScreen />));
    expect(await findByText('No requests yet')).toBeTruthy();
  });

  it('renders request cards and the status summary when data is present', async () => {
    mockEndpoints({
      requests: {
        items: [
          { request_id: 'r1', doc_type: 'FORM_16', employer_name: 'TechCorp', status: 'PENDING', created_at: '2024-01-01T00:00:00Z' },
          { request_id: 'r2', doc_type: 'SALARY_SLIP', employer_name: 'OldCo', status: 'FULFILLED', created_at: '2024-02-01T00:00:00Z' },
        ],
        total: 2,
      },
    });
    const { findByText, getByText } = await render(wrap(<DocRequestScreen />));
    expect(await findByText('TechCorp')).toBeTruthy();
    expect(getByText('OldCo')).toBeTruthy();
    // status badge text is uppercased status; summary row also shows the labels
    expect(getByText('FORM 16')).toBeTruthy();
  });
});
