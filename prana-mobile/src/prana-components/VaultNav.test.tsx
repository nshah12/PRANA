/**
 * VaultNav tests — renders all 5 tabs, marks the active one, and reports presses.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react-native';
import { VaultNav } from './VaultNav';
import { colors } from '../prana-theme/tokens';

function flatStyle(node: any) {
  const s = node.props.style;
  return Array.isArray(s) ? Object.assign({}, ...s.filter(Boolean)) : s;
}

describe('VaultNav', () => {
  it('renders all five tab labels', async () => {
    await render(<VaultNav active="vault" onPress={jest.fn()} />);
    for (const label of ['Vault', 'Activity', 'Career', 'Shares', 'Settings']) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it('reports the pressed tab key via onPress', async () => {
    const onPress = jest.fn();
    await render(<VaultNav active="vault" onPress={onPress} />);
    fireEvent.press(screen.getByText('Career'));
    expect(onPress).toHaveBeenCalledWith('career');
  });

  it('styles the active tab label with the indigo accent', async () => {
    await render(<VaultNav active="shares" onPress={jest.fn()} />);
    expect(flatStyle(screen.getByText('Shares')).color).toBe(colors.indigo);
    // A non-active label keeps the muted ink colour.
    expect(flatStyle(screen.getByText('Vault')).color).not.toBe(colors.indigo);
  });
});
