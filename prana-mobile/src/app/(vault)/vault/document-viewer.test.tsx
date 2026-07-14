/**
 * DocumentViewerScreen tests — loading/error/not-found states, download,
 * the share sheet (fixed createShare contract: share_token not share_url),
 * and the Career Passport modal. Share/download/credential calls are
 * mocked at the @/hooks/useVault boundary; their own contracts are covered
 * in useVault.test.ts.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import DocumentViewerScreen from './document-viewer';
import { useDocument, getDownloadUrl, createShare, getCredential } from '@/hooks/useVault';
import { useAuth } from '@/context/AuthContext';
import { router, useLocalSearchParams } from 'expo-router';
import { Linking } from 'react-native';

jest.mock('@/hooks/useVault', () => ({
  useDocument: jest.fn(),
  getDownloadUrl: jest.fn(),
  createShare: jest.fn(),
  getCredential: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
  useLocalSearchParams: jest.fn(),
}));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockUseDocument = useDocument as jest.Mock;
const mockGetDownloadUrl = getDownloadUrl as jest.Mock;
const mockCreateShare = createShare as jest.Mock;
const mockGetCredential = getCredential as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;
const mockUseParams = useLocalSearchParams as jest.Mock;

const DOC = {
  id: 'doc-1', title: 'April Salary Slip', issuer: 'NPCI',
  source_type: 'EMPLOYER_PUSH', received_at: '2026-04-01T00:00:00Z',
  icon_type: 'salary', icon_emoji: '💰', file_hash: 'abc123',
  insights: { Designation: { value: 'Engineer', confidence: 0.9 } },
};

afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseParams.mockReturnValue({ id: 'doc-1' });
  mockUseAuth.mockReturnValue({ profile: { vault_url: 'prana.in/asha' } });
  jest.spyOn(Linking, 'openURL').mockResolvedValue(true as any);
});

describe('DocumentViewerScreen — states', () => {
  it('shows the loading state', async () => {
    mockUseDocument.mockReturnValue({ data: null, loading: true, error: null });
    const rtl = await render(<DocumentViewerScreen />);
    expect(await rtl.findByText('Loading document…')).toBeTruthy();
  });

  it('shows a load-failed state with a back button', async () => {
    mockUseDocument.mockReturnValue({ data: null, loading: false, error: 'boom' });
    const rtl = await render(<DocumentViewerScreen />);
    expect(await rtl.findByText("Couldn't load document")).toBeTruthy();
    fireEvent.press(await rtl.findByText('← Go back'));
    expect(router.back).toHaveBeenCalled();
  });

  it('shows a not-found state when the document is missing', async () => {
    mockUseDocument.mockReturnValue({ data: null, loading: false, error: null });
    const rtl = await render(<DocumentViewerScreen />);
    expect(await rtl.findByText('Document not found')).toBeTruthy();
  });

  it('renders the document title, issuer, and insights once loaded', async () => {
    mockUseDocument.mockReturnValue({ data: { document: DOC }, loading: false, error: null });
    const rtl = await render(<DocumentViewerScreen />);
    expect(await rtl.findByText('Engineer')).toBeTruthy();
    expect((await rtl.findAllByText('April Salary Slip')).length).toBeGreaterThan(0);
  });
});

describe('DocumentViewerScreen — download', () => {
  beforeEach(() => mockUseDocument.mockReturnValue({ data: { document: DOC }, loading: false, error: null }));

  it('downloads via getDownloadUrl and opens the returned URL', async () => {
    mockGetDownloadUrl.mockResolvedValue('https://cdn.prana.in/doc-1.pdf');
    const rtl = await render(<DocumentViewerScreen />);
    fireEvent.press(await rtl.findByText('⬇'));
    await waitFor(() => expect(mockGetDownloadUrl).toHaveBeenCalledWith('doc-1'));
    await waitFor(() => expect(Linking.openURL).toHaveBeenCalledWith('https://cdn.prana.in/doc-1.pdf'));
  });
});

describe('DocumentViewerScreen — share sheet', () => {
  beforeEach(() => mockUseDocument.mockReturnValue({ data: { document: DOC }, loading: false, error: null }));

  it('opens automatically via ?action=share', async () => {
    mockUseParams.mockReturnValue({ id: 'doc-1', action: 'share' });
    const rtl = await render(<DocumentViewerScreen />);
    expect(await rtl.findByText('Share document')).toBeTruthy();
  });

  it('creates a share link with the corrected contract and displays the share_token', async () => {
    mockCreateShare.mockResolvedValue({ share_id: 's-1', share_token: 'tok-xyz', expires_at: '2026-08-01T00:00:00Z', otp_required: false });
    const rtl = await render(<DocumentViewerScreen />);
    fireEvent.press(await rtl.findByText('↗', {}, {}));
    fireEvent.press(await rtl.findByText('Create share link →'));
    await waitFor(() => expect(mockCreateShare).toHaveBeenCalledWith({
      document_ids: ['doc-1'], recipient_label: undefined, expires_hours: 168,
    }));
    expect(await rtl.findByText('tok-xyz')).toBeTruthy();
  });

  it('shows an error when share creation fails', async () => {
    mockCreateShare.mockRejectedValue(new Error('boom'));
    const rtl = await render(<DocumentViewerScreen />);
    fireEvent.press(await rtl.findByText('↗', {}, {}));
    fireEvent.press(await rtl.findByText('Create share link →'));
    expect(await rtl.findByText("Couldn't create share link. Check your connection and try again.")).toBeTruthy();
  });
});

describe('DocumentViewerScreen — Career Passport modal', () => {
  beforeEach(() => mockUseDocument.mockReturnValue({ data: { document: DOC }, loading: false, error: null }));

  it('loads and displays the credential card', async () => {
    mockGetCredential.mockResolvedValue({
      verification_code: 'ABCD-1234', verify_url: 'https://prana.in/verify/abcd',
      qr_url: '/qr/abcd', doc_type: 'SALARY_SLIP', doc_period: 'Apr 2026',
      pushed_by: 'NPCI', pushed_at: null, routed_at: null, file_hash_sha256: null,
    });
    const rtl = await render(<DocumentViewerScreen />);
    fireEvent.press(await rtl.findByText('Verify'));
    expect(await rtl.findByText('ABCD-1234')).toBeTruthy();
    expect(mockGetCredential).toHaveBeenCalledWith('doc-1');
  });

  it('shows a processing message when the credential is not yet available', async () => {
    mockGetCredential.mockRejectedValue(new Error('boom'));
    const rtl = await render(<DocumentViewerScreen />);
    fireEvent.press(await rtl.findByText('Verify'));
    expect(await rtl.findByText('Credential not available yet — document is still processing.')).toBeTruthy();
  });
});
