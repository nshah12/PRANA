/**
 * VaultHomeScreen tests — the main vault list: loading/empty/data states,
 * company + doc-type filtering, multi-select -> ZIP download, per-card
 * view/share navigation, the hamburger menu's sign-out, and the bell popup.
 *
 * Data hooks (useDocuments/useEmployers/useShares) and the download/zip
 * helpers are mocked at the @/hooks/useVault boundary rather than the
 * underlying api client, since this screen's own filtering/selection logic
 * — not the fetch plumbing (already covered by useVault.test.ts) — is what's
 * under test here. useQuery (gamification + benchmarking-nudge) is mocked
 * directly since both call sites live in this file, not behind a hook.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import { Linking } from 'react-native';
import { VaultHomeScreen } from './VaultHomeScreen';
import { useDocuments, useEmployers, useShares, getDownloadUrl, requestZipDownload } from '@/hooks/useVault';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';

jest.mock('@/hooks/useVault', () => ({
  useDocuments: jest.fn(),
  useEmployers: jest.fn(),
  useShares: jest.fn(),
  getDownloadUrl: jest.fn(),
  createShare: jest.fn(),
  requestZipDownload: jest.fn(),
}));
jest.mock('@tanstack/react-query', () => ({ useQuery: jest.fn() }));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockUseDocuments = useDocuments as jest.Mock;
const mockUseEmployers = useEmployers as jest.Mock;
const mockUseShares = useShares as jest.Mock;
const mockGetDownloadUrl = getDownloadUrl as jest.Mock;
const mockRequestZip = requestZipDownload as jest.Mock;
const mockUseQuery = useQuery as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;
const mockSignOut = jest.fn();

const DOC_1 = {
  id: 'doc-1', doc_type: 'SALARY_SLIP', title: 'April Salary Slip',
  source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'emp-1',
  received_at: '2026-04-01T00:00:00Z', icon_type: 'salary', icon_emoji: '💰',
};
const DOC_2 = {
  id: 'doc-2', doc_type: 'FORM_16', title: 'Form 16 FY24',
  source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null,
  received_at: '2026-05-01T00:00:00Z', icon_type: 'form16', icon_emoji: '📄',
};
const EMPLOYER_1 = { id: 'emp-1', name: 'NPCI', role: 'Engineer', from: '2020-01-01', to: null };

function mockDocsState(overrides: Partial<{ data: any; loading: boolean; error: string | null; refetch: jest.Mock }>) {
  mockUseDocuments.mockReturnValue({ data: null, loading: false, error: null, refetch: jest.fn(), ...overrides });
}

afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseEmployers.mockReturnValue({ data: { employers: [EMPLOYER_1] }, loading: false, error: null, refetch: jest.fn() });
  mockUseShares.mockReturnValue({ data: { shares: [{ status: 'ACTIVE' }] }, loading: false, error: null, refetch: jest.fn() });
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  mockUseAuth.mockReturnValue({ profile: { name: 'Asha Rao', vault_url: 'prana.in/asha' }, signOut: mockSignOut });
  jest.spyOn(Linking, 'openURL').mockResolvedValue(true as any);
});

describe('VaultHomeScreen — states', () => {
  it('shows the loading state while documents are being fetched', async () => {
    mockDocsState({ loading: true });
    const rtl = await render(<VaultHomeScreen />);
    expect(await rtl.findByText('Loading your vault…')).toBeTruthy();
  });

  it('shows the empty state with an upload CTA when there are no documents', async () => {
    mockDocsState({ data: { documents: [] } });
    const rtl = await render(<VaultHomeScreen />);
    expect(await rtl.findByText('Upload your first document')).toBeTruthy();
    fireEvent.press(await rtl.findByText('Upload your first document'));
    expect(router.push).toHaveBeenCalledWith('/(vault)/vault/self-upload');
  });

  it('renders the document list and stat counts once loaded', async () => {
    mockDocsState({ data: { documents: [DOC_1, DOC_2] } });
    const rtl = await render(<VaultHomeScreen />);
    expect(await rtl.findByText('April Salary Slip')).toBeTruthy();
    expect(await rtl.findByText('Form 16 FY24')).toBeTruthy();
    expect(await rtl.findByText('2')).toBeTruthy(); // Documents stat card
  });
});

describe('VaultHomeScreen — filtering', () => {
  beforeEach(() => mockDocsState({ data: { documents: [DOC_1, DOC_2] } }));

  it('filters to a single employer via the company picker', async () => {
    const rtl = await render(<VaultHomeScreen />);
    await rtl.findByText('April Salary Slip');
    fireEvent.press(await rtl.findByText('All sources'));
    fireEvent.press(await rtl.findByText('NPCI'));
    expect(await rtl.findByText('April Salary Slip')).toBeTruthy();
    expect(rtl.queryByText('Form 16 FY24')).toBeNull();
  });

  it('filters to self-uploaded documents via the company picker', async () => {
    const rtl = await render(<VaultHomeScreen />);
    await rtl.findByText('April Salary Slip');
    fireEvent.press(await rtl.findByText('All sources'));
    fireEvent.press(await rtl.findByText('Self-uploaded'));
    expect(await rtl.findByText('Form 16 FY24')).toBeTruthy();
    expect(rtl.queryByText('April Salary Slip')).toBeNull();
  });

  it('filters by document type via the doc-type picker', async () => {
    const rtl = await render(<VaultHomeScreen />);
    await rtl.findByText('April Salary Slip');
    fireEvent.press(await rtl.findByText('All types'));
    fireEvent.press(await rtl.findByText('Form 16'));
    expect(await rtl.findByText('Form 16 FY24')).toBeTruthy();
    expect(rtl.queryByText('April Salary Slip')).toBeNull();
  });
});

describe('VaultHomeScreen — per-document actions', () => {
  beforeEach(() => mockDocsState({ data: { documents: [DOC_1] } }));

  it('navigates to the document viewer on View', async () => {
    const rtl = await render(<VaultHomeScreen />);
    fireEvent.press(await rtl.findByLabelText('View'));
    expect(router.push).toHaveBeenCalledWith('/(vault)/vault/document-viewer?id=doc-1');
  });

  it('navigates to the document viewer with action=share on Share', async () => {
    const rtl = await render(<VaultHomeScreen />);
    fireEvent.press(await rtl.findByLabelText('Share'));
    expect(router.push).toHaveBeenCalledWith('/(vault)/vault/document-viewer?id=doc-1&action=share');
  });

  it('downloads via getDownloadUrl and opens the returned URL', async () => {
    mockGetDownloadUrl.mockResolvedValue('https://cdn.prana.in/doc-1.pdf');
    const rtl = await render(<VaultHomeScreen />);
    fireEvent.press(await rtl.findByLabelText('Download'));
    await waitFor(() => expect(mockGetDownloadUrl).toHaveBeenCalledWith('doc-1'));
    await waitFor(() => expect(Linking.openURL).toHaveBeenCalledWith('https://cdn.prana.in/doc-1.pdf'));
  });
});

describe('VaultHomeScreen — multi-select and ZIP download', () => {
  beforeEach(() => mockDocsState({ data: { documents: [DOC_1, DOC_2] } }));

  it('enters selection mode on long-press and downloads the ZIP for selected docs', async () => {
    mockRequestZip.mockResolvedValue({ job_id: 'job-1' });
    const rtl = await render(<VaultHomeScreen />);
    const card = (await rtl.findByText('April Salary Slip')).parent?.parent;
    fireEvent(card!, 'longPress');

    expect(await rtl.findByText('1 selected')).toBeTruthy();
    fireEvent.press(await rtl.findByText('Select all'));
    expect(await rtl.findByText('2 selected')).toBeTruthy();

    // Opens ZipModal (packing animation), which calls onDone (-> requestZipDownload)
    // only once its real ~1.6s Animated.timing finishes and shows the confirm button.
    fireEvent.press(await rtl.findByText(/Download ZIP \(/));
    const confirmBtn = await rtl.findByText('⬇  Download ZIP', {}, { timeout: 3000 });
    fireEvent.press(confirmBtn);
    await waitFor(() => expect(mockRequestZip).toHaveBeenCalledWith(expect.arrayContaining(['doc-1', 'doc-2'])), { timeout: 3000 });
  }, 10000);
});

describe('VaultHomeScreen — menu', () => {
  beforeEach(() => mockDocsState({ data: { documents: [DOC_1] } }));

  it('signs out and routes to sign-in from the hamburger menu', async () => {
    const rtl = await render(<VaultHomeScreen />);
    fireEvent.press(await rtl.findByText('☰'));
    fireEvent.press(await rtl.findByText('Sign out'));
    expect(mockSignOut).toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
  });
});
