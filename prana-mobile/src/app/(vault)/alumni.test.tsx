/**
 * AlumniScreen tests — Past Employers tab loading/empty/happy states,
 * and the Inbox tab unread badge.
 */
import React from 'react';
import { render, cleanup, fireEvent } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AlumniScreen from './alumni';
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

function mockEndpoints({ employers, outreach = { items: [] } }: any) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/alumni/employers') return Promise.resolve(employers);
    if (url === '/v1/alumni/outreach') return Promise.resolve(outreach);
    return Promise.reject(new Error('unexpected url ' + url));
  });
}

describe('AlumniScreen', () => {
  it('renders the header and defaults to the Past Employers tab', async () => {
    mockEndpoints({ employers: { items: [] } });
    const { getByText, findByText } = await render(wrap(<AlumniScreen />));
    expect(getByText('Alumni Connect')).toBeTruthy();
    expect(await findByText('No past employers found')).toBeTruthy();
  });

  it('renders past employer cards with the consent control copy', async () => {
    mockEndpoints({
      employers: {
        items: [{
          tenant_id: 't1', employee_uuid: 'e1', company_name: 'TechCorp',
          designation: 'Engineer', department: 'Eng', doj: '2020-01-01', dol: '2022-01-01',
          tenure_band: '2-3 yrs', granted: false, share_mobile: false, share_email: false,
        }],
      },
    });
    const { findByText, getByText } = await render(wrap(<AlumniScreen />));
    expect(await findByText('TechCorp')).toBeTruthy();
    expect(getByText('You control who can find you')).toBeTruthy();
  });

  it('shows the unread count badge after switching to the Inbox tab', async () => {
    // The outreach query is `enabled: tab === 'inbox'` — it never fires on the
    // default (consent) tab, so the badge only appears after the tab switch.
    mockEndpoints({
      employers: { items: [] },
      outreach: { items: [
        { outreach_id: 'o1', company_name: 'TechCorp', subject: 'Hi', body_text: 'x', status: 'SENT',
          sent_at: '2024-01-01T00:00:00Z', read_at: null, reply_body: null, replied_at: null },
      ] },
    });
    const { findByText, getByText } = await render(wrap(<AlumniScreen />));
    await findByText('No past employers found'); // wait for initial (consent) load to settle
    fireEvent.press(getByText(/^Inbox/));
    // The outreach query only becomes `enabled` after this tab switch, so give it
    // extra time to fetch and re-render beyond RTL's default 1000ms poll window.
    expect(await findByText(/Inbox \(1\)/, {}, { timeout: 5000 })).toBeTruthy();
  });
});
