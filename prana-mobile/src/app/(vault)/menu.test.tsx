/**
 * MenuModal tests — profile summary row + menu item navigation + sign-out.
 */
import React from 'react';
import { render, cleanup, fireEvent } from '@testing-library/react-native';
import MenuModal from './menu';
import { useAuth } from '@/context/AuthContext';
import { router } from 'expo-router';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({ router: { back: jest.fn(), push: jest.fn(), replace: jest.fn() } }));

const mockUseAuth = useAuth as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => jest.clearAllMocks());

describe('MenuModal', () => {
  it('shows "Loading…" for the profile line before profile data is available', async () => {
    mockUseAuth.mockReturnValue({ profile: null, signOut: jest.fn() });
    const { getByText } = await render(<MenuModal />);
    expect(getByText('Loading…')).toBeTruthy();
    expect(getByText('—')).toBeTruthy(); // name fallback
  });

  it('renders the profile summary line once loaded', async () => {
    mockUseAuth.mockReturnValue({
      profile: { name: 'Priya Sharma', active_since: '2020-01-01', employer_count: 2 },
      signOut: jest.fn(),
    });
    const { getByText } = await render(<MenuModal />);
    expect(getByText('Priya Sharma')).toBeTruthy();
    expect(getByText(/2 employers/)).toBeTruthy();
  });

  it('renders every menu item label', async () => {
    mockUseAuth.mockReturnValue({ profile: null, signOut: jest.fn() });
    const { getByText } = await render(<MenuModal />);
    for (const label of ['My Vault', 'Career', 'Vault Health', 'Doc Requests', 'Shares',
      'Alumni Connect', 'Comp Benchmark', 'Privacy', 'Settings']) {
      expect(getByText(label)).toBeTruthy();
    }
  });

  it('navigates and closes the modal when a menu item is pressed', async () => {
    mockUseAuth.mockReturnValue({ profile: null, signOut: jest.fn() });
    const { getByText } = await render(<MenuModal />);
    fireEvent.press(getByText('Career'));
    expect(router.push).toHaveBeenCalledWith('/(vault)/career');
    expect(router.back).toHaveBeenCalled();
  });

  it('signs out and replaces the route when Sign out is pressed', async () => {
    const signOut = jest.fn();
    mockUseAuth.mockReturnValue({ profile: null, signOut });
    const { getByText } = await render(<MenuModal />);
    fireEvent.press(getByText('Sign out'));
    expect(signOut).toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
  });
});
