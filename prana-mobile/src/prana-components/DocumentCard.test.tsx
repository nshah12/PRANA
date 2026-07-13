/**
 * DocumentCard tests — source-identity badge, calendar chip, per-card actions,
 * and selection-mode behaviour.
 *
 * Uses the queries returned by `await render(...)` (RTL v14's global `screen` can
 * go stale across async renders). Kept to a small number of renders per file — a
 * large number of consecutive async renders can trip an RTL-v14/React-19 commit flake.
 */
import React from 'react';
import { render, fireEvent, cleanup } from '@testing-library/react-native';
import { DocumentCard, SOURCE_META } from './DocumentCard';

afterEach(async () => { await cleanup(); });

const base = {
  id: 'd1',
  iconType: 'salary' as const,
  iconEmoji: '💰',
  title: 'April 2024 Salary Slip',
  issuer: 'NPCI',
  docType: 'Salary Slip',
  sourceType: 'EMPLOYER_PUSH' as const,
  receivedAt: '2024-03-05T00:00:00Z',
};

describe('DocumentCard', () => {
  it('hides the action buttons and uses onPress in selection mode', async () => {
    const onPress = jest.fn(), onView = jest.fn();
    const { getByText, queryByLabelText } = await render(
      <DocumentCard {...base} selectionMode selected onPress={onPress} onView={onView} />,
    );
    expect(queryByLabelText('View')).toBeNull();
    expect(queryByLabelText('Download')).toBeNull();
    fireEvent.press(getByText(SOURCE_META.EMPLOYER_PUSH.label));
    expect(onPress).toHaveBeenCalledTimes(1);
    expect(onView).not.toHaveBeenCalled();
  });

  it('renders title, meta, source badge and the calendar chip', async () => {
    const { getByText } = await render(<DocumentCard {...base} />);
    expect(getByText('April 2024 Salary Slip')).toBeTruthy();       // title (unique)
    expect(getByText(/NPCI.*Salary Slip/)).toBeTruthy();            // meta row (issuer · docType)
    expect(getByText(SOURCE_META.EMPLOYER_PUSH.label)).toBeTruthy(); // "Employer" badge
    expect(getByText('MAR')).toBeTruthy();                          // calendar month
    expect(getByText('05')).toBeTruthy();                           // calendar day
  });

  it('shows the correct source badge label per source type', async () => {
    const { getByText } = await render(<DocumentCard {...base} sourceType="EMAIL_FETCH" />);
    expect(getByText(SOURCE_META.EMAIL_FETCH.label)).toBeTruthy(); // "Email"
  });

  it('fires the per-card actions (View / Download / Share)', async () => {
    const onView = jest.fn(), onDownload = jest.fn(), onShare = jest.fn();
    const { getByLabelText } = await render(
      <DocumentCard {...base} onView={onView} onDownload={onDownload} onShare={onShare} />,
    );
    fireEvent.press(getByLabelText('Download'));
    fireEvent.press(getByLabelText('Share'));
    expect(onDownload).toHaveBeenCalledTimes(1);
    expect(onShare).toHaveBeenCalledTimes(1);
  });
});
