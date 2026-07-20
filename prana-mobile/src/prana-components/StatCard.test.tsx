/**
 * StatCard render test — proves the @testing-library/react-native + jest-expo
 * component-rendering path works end to end (RN transforms, theme tokens, RTL queries).
 *
 * NOTE: RTL-React-Native v14 (React 19 support) makes render/rerender/unmount ASYNC
 * — they must be awaited. Older RTL snippets that destructure `render(...)` directly
 * will silently get a Promise with no query methods.
 */
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { StatCard } from './StatCard';

describe('StatCard', () => {
  it('renders the value and label', async () => {
    await render(<StatCard value={42} label="Documents" accent="indigo" />);
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.getByText('Documents')).toBeTruthy();
  });

  it('renders a string value as-is', async () => {
    await render(<StatCard value="—" label="Shares" accent="emerald" />);
    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.getByText('Shares')).toBeTruthy();
  });

  it('colours the number by accent (emerald)', async () => {
    await render(<StatCard value={1} label="A" accent="emerald" />);
    const num = screen.getByText('1');
    const flat = Array.isArray(num.props.style) ? Object.assign({}, ...num.props.style) : num.props.style;
    expect(flat.color).toBe('#10B981');
  });
});
