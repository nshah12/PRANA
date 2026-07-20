/**
 * CreateShareScreen tests — document selection/search, expiry picker,
 * and the create flow. createShare() is mocked at the @/hooks/useVault
 * boundary; its own real contract (POST /v1/vault/share, share_token not
 * share_url) is covered separately in useVault.test.ts.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import CreateShareScreen from './create-share';
import { useDocuments, createShare } from '@/hooks/useVault';
import { router, useLocalSearchParams } from 'expo-router';

jest.mock('@/hooks/useVault', () => ({
  useDocuments: jest.fn(),
  createShare: jest.fn(),
}));
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

const mockUseDocuments = useDocuments as jest.Mock;
const mockCreateShare = createShare as jest.Mock;
const mockUseParams = useLocalSearchParams as jest.Mock;

const DOC_1 = { id: 'doc-1', doc_type: 'SALARY_SLIP', title: 'April Salary Slip', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'emp-1', received_at: '2026-04-01T00:00:00Z' };
const DOC_2 = { id: 'doc-2', doc_type: 'FORM_16', title: 'Form 16 FY24', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2026-05-01T00:00:00Z' };

afterEach(async () => { await cleanup(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseParams.mockReturnValue({});
  mockUseDocuments.mockReturnValue({ data: { documents: [DOC_1, DOC_2] }, loading: false });
});

describe('CreateShareScreen', () => {
  it('disables the create button until at least one document is selected', async () => {
    const rtl = await render(<CreateShareScreen />);
    expect(await rtl.findByText('Select documents to share')).toBeTruthy();
  });

  it('pre-selects a document passed via the preselect param', async () => {
    mockUseParams.mockReturnValue({ preselect: 'doc-1' });
    const rtl = await render(<CreateShareScreen />);
    expect(await rtl.findByText('Create link for 1 document →')).toBeTruthy();
  });

  it('selecting a document updates the selected count and enables the CTA', async () => {
    const rtl = await render(<CreateShareScreen />);
    fireEvent.press(await rtl.findByText('April Salary Slip'));
    expect(await rtl.findByText('Create link for 1 document →')).toBeTruthy();
  });

  it('filters the document list by search text', async () => {
    const rtl = await render(<CreateShareScreen />);
    const search = await rtl.findByPlaceholderText('Search by title or company…');
    fireEvent.changeText(search, 'form 16');
    expect(await rtl.findByText('Form 16 FY24')).toBeTruthy();
    expect(rtl.queryByText('April Salary Slip')).toBeNull();
  });

  it('creates a share with the selected documents and expiry, then shows the created sheet', async () => {
    mockCreateShare.mockResolvedValue({ share_id: 's-1', share_token: 'tok-abc', expires_at: '2026-08-01T00:00:00Z', otp_required: false });
    const rtl = await render(<CreateShareScreen />);
    fireEvent.press(await rtl.findByText('April Salary Slip'));
    fireEvent.press(await rtl.findByText('30 days'));
    fireEvent.press(await rtl.findByText('Create link for 1 document →'));

    await waitFor(() => expect(mockCreateShare).toHaveBeenCalledWith(expect.objectContaining({
      document_ids: ['doc-1'],
      expires_hours: 720,
    })));
    expect(await rtl.findByText('tok-abc')).toBeTruthy();
  });

  it('shows an error message when share creation fails', async () => {
    mockCreateShare.mockRejectedValue(new Error('boom'));
    const rtl = await render(<CreateShareScreen />);
    fireEvent.press(await rtl.findByText('April Salary Slip'));
    fireEvent.press(await rtl.findByText('Create link for 1 document →'));
    expect(await rtl.findByText("Couldn't create share link. Check your connection and try again.")).toBeTruthy();
  });

  it('routes back to shares once the created sheet is dismissed', async () => {
    mockCreateShare.mockResolvedValue({ share_id: 's-1', share_token: 'tok-abc', expires_at: '2026-08-01T00:00:00Z', otp_required: false });
    const rtl = await render(<CreateShareScreen />);
    fireEvent.press(await rtl.findByText('April Salary Slip'));
    fireEvent.press(await rtl.findByText('Create link for 1 document →'));
    fireEvent.press(await rtl.findByText('Done'));
    expect(router.replace).toHaveBeenCalledWith('/(vault)/shares');
  });
});
