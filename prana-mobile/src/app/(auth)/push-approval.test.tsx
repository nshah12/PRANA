/**
 * PushApprovalScreen tests — this screen's three backend endpoints
 * (push-status/push-approve/push-deny) don't exist yet (see TODO(backend) in
 * push-approval.tsx), so these tests exercise the screen's own state machine
 * against the documented mock shape rather than a live contract: missing
 * session_id, pending -> approve, pending -> deny, and deny-fails-optimistically
 * (the one deliberately fail-open path in this screen, by design).
 */
import React from 'react';
import { render, cleanup, fireEvent, waitFor } from '@testing-library/react-native';
import PushApprovalScreen from './push-approval';
import { api } from '@/lib/api';
import { router, useLocalSearchParams } from 'expo-router';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn() } }));
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

const mockGet = api.get as jest.Mock;
const mockPost = api.post as jest.Mock;
const mockUseParams = useLocalSearchParams as jest.Mock;

const REQUEST = {
  session_id: 'sess-1',
  device_name: 'Chrome on Windows',
  browser: 'Chrome',
  location: 'Mumbai, IN',
  ip_masked: '49.x.x.12',
  requested_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 120000).toISOString(),
};

afterEach(async () => { await cleanup(); jest.useRealTimers(); });
beforeEach(() => {
  jest.clearAllMocks();
  mockUseParams.mockReturnValue({ session_id: 'sess-1' });
});

describe('PushApprovalScreen', () => {
  it('shows an error and never polls when there is no session_id param', async () => {
    mockUseParams.mockReturnValue({});
    const rtl = await render(<PushApprovalScreen />);
    expect(await rtl.findByText('No login request found. This link may have expired.')).toBeTruthy();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('loads a pending request and shows its details', async () => {
    mockGet.mockResolvedValue({ status: 'pending', request: REQUEST });
    const rtl = await render(<PushApprovalScreen />);
    expect(mockGet).toHaveBeenCalledWith('/auth/employee/device/push-status?session_id=sess-1');
    expect(await rtl.findByText('Someone wants in.')).toBeTruthy();
    expect(await rtl.findByText('Chrome')).toBeTruthy();
  });

  it('approves the request and shows the approved state', async () => {
    mockGet.mockResolvedValue({ status: 'pending', request: REQUEST });
    mockPost.mockResolvedValue({});
    const rtl = await render(<PushApprovalScreen />);
    fireEvent.press(await rtl.findByText("Yes, it's me →"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/auth/employee/device/push-approve', { session_id: 'sess-1' }));
    expect(await rtl.findByText('Access approved')).toBeTruthy();
  });

  it('denies the request and shows the denied state', async () => {
    mockGet.mockResolvedValue({ status: 'pending', request: REQUEST });
    mockPost.mockResolvedValue({});
    const rtl = await render(<PushApprovalScreen />);
    fireEvent.press(await rtl.findByText('Not me — Deny'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/auth/employee/device/push-deny', { session_id: 'sess-1' }));
    expect(await rtl.findByText('Access denied')).toBeTruthy();
  });

  it('still shows denied even when the deny call fails (fail-safe by design)', async () => {
    mockGet.mockResolvedValue({ status: 'pending', request: REQUEST });
    mockPost.mockRejectedValue(new Error('network down'));
    const rtl = await render(<PushApprovalScreen />);
    fireEvent.press(await rtl.findByText('Not me — Deny'));
    expect(await rtl.findByText('Access denied')).toBeTruthy();
  });

  it('shows the expired state for an already-expired request', async () => {
    mockGet.mockResolvedValue({ status: 'expired', request: REQUEST });
    const rtl = await render(<PushApprovalScreen />);
    expect(await rtl.findByText('Request expired')).toBeTruthy();
  });
});
