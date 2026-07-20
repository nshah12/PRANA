/**
 * SelfUploadScreen tests — file pick -> doc-type selection -> upload state
 * machine. api.upload() is mocked; the real backend contract for this
 * screen doesn't exist yet (see TODO(backend) in self-upload.tsx — the only
 * upload route is the OA-Operator-only /ingest/upload), so these tests
 * exercise the screen's own logic against the documented placeholder call.
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import SelfUploadScreen from './self-upload';
import { api } from '@/lib/api';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

jest.mock('@/lib/api', () => ({ api: { upload: jest.fn() } }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() } }));
jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: ({ children, ...props }: any) => React.createElement(View, props, children),
    SafeAreaProvider: ({ children }: any) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

const mockUpload = api.upload as jest.Mock;
const mockGetDocumentAsync = DocumentPicker.getDocumentAsync as jest.Mock;
const FILE_ASSET = { uri: 'file:///tmp/slip.pdf', name: 'slip.pdf', size: 51200, mimeType: 'application/pdf' };

afterEach(async () => { await cleanup(); });
beforeEach(() => { jest.clearAllMocks(); });

describe('SelfUploadScreen', () => {
  it('shows "Pick a document first" until a file is chosen', async () => {
    const rtl = await render(<SelfUploadScreen />);
    expect(await rtl.findByText('Pick a document first')).toBeTruthy();
  });

  it('picks a file and shows "Choose document type" until a type is selected', async () => {
    mockGetDocumentAsync.mockResolvedValue({ canceled: false, assets: [FILE_ASSET] });
    const rtl = await render(<SelfUploadScreen />);
    fireEvent.press(await rtl.findByText('Tap to pick a document'));
    expect(await rtl.findByText('slip.pdf')).toBeTruthy();
    expect(await rtl.findByText('Choose document type')).toBeTruthy();
  });

  it('shows an error when the file picker itself fails', async () => {
    mockGetDocumentAsync.mockRejectedValue(new Error('picker crashed'));
    const rtl = await render(<SelfUploadScreen />);
    fireEvent.press(await rtl.findByText('Tap to pick a document'));
    expect(await rtl.findByText("Couldn't open file picker. Please try again.")).toBeTruthy();
  });

  it('does nothing when the user cancels the picker', async () => {
    mockGetDocumentAsync.mockResolvedValue({ canceled: true, assets: [] });
    const rtl = await render(<SelfUploadScreen />);
    fireEvent.press(await rtl.findByText('Tap to pick a document'));
    expect(await rtl.findByText('Pick a document first')).toBeTruthy();
  });

  it('enables the CTA once a file and doc type are both chosen, then uploads', async () => {
    mockGetDocumentAsync.mockResolvedValue({ canceled: false, assets: [FILE_ASSET] });
    mockUpload.mockResolvedValue({ document_id: 'doc-1' });
    const rtl = await render(<SelfUploadScreen />);
    fireEvent.press(await rtl.findByText('Tap to pick a document'));
    fireEvent.press(await rtl.findByText('Salary Slip'));
    fireEvent.press(await rtl.findByText('Add to vault →'));

    await waitFor(() => expect(mockUpload).toHaveBeenCalled());
    const [path, formData] = mockUpload.mock.calls[0];
    expect(path).toBe('/vault/documents/upload');
    expect(formData).toBeInstanceOf(FormData);

    expect(await rtl.findByText('✓  Uploaded to your vault')).toBeTruthy();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/(vault)/vault'), { timeout: 3000 });
  }, 10000);

  it('shows an error message when the upload call fails', async () => {
    mockGetDocumentAsync.mockResolvedValue({ canceled: false, assets: [FILE_ASSET] });
    mockUpload.mockRejectedValue(new Error('network down'));
    const rtl = await render(<SelfUploadScreen />);
    fireEvent.press(await rtl.findByText('Tap to pick a document'));
    fireEvent.press(await rtl.findByText('Salary Slip'));
    fireEvent.press(await rtl.findByText('Add to vault →'));
    expect(await rtl.findByText('Upload failed. Check your connection and try again.')).toBeTruthy();
  });

  it('reveals a password field when "password-protected" is toggled on', async () => {
    const rtl = await render(<SelfUploadScreen />);
    expect(rtl.queryByPlaceholderText('PDF password…')).toBeNull();
    fireEvent.press(await rtl.findByText('This PDF is password-protected'));
    expect(await rtl.findByPlaceholderText('PDF password…')).toBeTruthy();
  });
});
