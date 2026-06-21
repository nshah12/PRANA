/**
 * DigestDatePicker tests — TDD RED → GREEN → REFACTOR
 *
 * Contract under test:
 *  1. Renders 4 tabs: This week / This month / This quarter / Custom
 *  2. Custom tab reveals from/to date inputs
 *  3. Date inputs are hidden when a preset tab is active
 *  4. Fires onChange with correct from/to when preset selected
 *  5. Shows inline constraint hint when Custom is active and no error
 *  6. Shows error (not API call) when range > 184 days
 *  7. Shows error when to_date is in the future
 *  8. Shows error when from_date >= to_date
 *  9. Shows error when lookback > 730 days
 * 10. Clears error and fires onChange when user corrects the range
 */
import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DigestDatePicker } from './DigestDatePicker'

function today() { return new Date().toISOString().split('T')[0] }
function daysAgo(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().split('T')[0]
}
function daysFromNow(n: number) {
  const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().split('T')[0]
}

const defaultProps = {
  accentColor:  'bg-indigo-600',
  accentText:   'text-indigo-600',
  accentBorder: 'border-indigo-600',
  onChange: vi.fn(),
}

beforeEach(() => { vi.clearAllMocks() })

describe('DigestDatePicker — tabs', () => {
  it('renders all 4 period tabs', () => {
    render(<DigestDatePicker {...defaultProps} />)
    expect(screen.getByRole('button', { name: /this week/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /this month/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /this quarter/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument()
  })

  it('does not show date inputs when a preset tab is active', () => {
    render(<DigestDatePicker {...defaultProps} />)
    expect(screen.queryByLabelText(/from/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/to/i)).not.toBeInTheDocument()
  })

  it('fires onChange on mount with weekly preset window', () => {
    render(<DigestDatePicker {...defaultProps} />)
    expect(defaultProps.onChange).toHaveBeenCalledTimes(1)
    const call = defaultProps.onChange.mock.calls[0][0]
    expect(call).toHaveProperty('from')
    expect(call).toHaveProperty('to')
    expect(call.to).toBe(today())
  })

  it('fires onChange with new window when monthly tab clicked', () => {
    render(<DigestDatePicker {...defaultProps} />)
    vi.clearAllMocks()
    fireEvent.click(screen.getByRole('button', { name: /this month/i }))
    expect(defaultProps.onChange).toHaveBeenCalledTimes(1)
    const call = defaultProps.onChange.mock.calls[0][0]
    expect(call.from).toBe(daysAgo(30))
    expect(call.to).toBe(today())
  })
})

describe('DigestDatePicker — custom range', () => {
  it('shows date inputs when Custom tab is clicked', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    expect(screen.getByLabelText(/from/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/to/i)).toBeInTheDocument()
  })

  it('shows constraint hint when custom active and no error', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    expect(screen.getByText(/max 6 months/i)).toBeInTheDocument()
  })

  it('fires onChange with exact dates when valid custom range entered', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    vi.clearAllMocks()
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: '2026-01-01' } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: '2026-01-31' } })
    expect(defaultProps.onChange).toHaveBeenCalledWith({ from: '2026-01-01', to: '2026-01-31' })
  })
})

describe('DigestDatePicker — bounds enforcement (no API call)', () => {
  it('shows error immediately when range exceeds 184 days', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: daysAgo(185) } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: today() } })
    expect(screen.getByText(/max range is 184 days/i)).toBeInTheDocument()
    // onChange must NOT be called with the invalid range
    const validCalls = defaultProps.onChange.mock.calls.filter(
      c => c[0].from === daysAgo(185)
    )
    expect(validCalls).toHaveLength(0)
  })

  it('shows error when to_date is in the future', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: daysAgo(7) } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: daysFromNow(1) } })
    expect(screen.getByText(/cannot be in the future/i)).toBeInTheDocument()
  })

  it('shows error when from_date >= to_date', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: today() } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: daysAgo(1) } })
    expect(screen.getByText(/start date must be before/i)).toBeInTheDocument()
  })

  it('shows error when lookback exceeds 730 days', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: daysAgo(731) } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: daysAgo(724) } })
    expect(screen.getByText(/2 years/i)).toBeInTheDocument()
  })

  it('clears error and fires onChange when range is corrected', () => {
    render(<DigestDatePicker {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /custom/i }))
    // set invalid range first
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: daysAgo(185) } })
    fireEvent.change(screen.getByLabelText(/to/i),   { target: { value: today() } })
    expect(screen.getByText(/max range is 184 days/i)).toBeInTheDocument()
    // correct it
    vi.clearAllMocks()
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: daysAgo(30) } })
    expect(screen.queryByText(/max range is 184 days/i)).not.toBeInTheDocument()
    expect(defaultProps.onChange).toHaveBeenCalledWith({ from: daysAgo(30), to: today() })
  })
})
