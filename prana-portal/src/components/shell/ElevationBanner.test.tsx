/**
 * ElevationBanner tests
 *
 * Contract under test (from src/components/shell/ElevationBanner.tsx):
 *  1. Renders the elevated-session message with a live countdown (h/m/s) to endsAt
 *  2. Countdown ticks down every second (setInterval)
 *  3. Shows "Expired" once endsAt has passed
 *  4. "End early" button fires the onEndEarly callback
 *
 * Used in src/App.tsx PortalLayout as:
 *   <ElevationBanner endsAt={activeElevation!.ends_at} onEndEarly={() => endEarlyMutation.mutate(...)} />
 */
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ElevationBanner } from './ElevationBanner'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ElevationBanner', () => {
  it('renders the elevated session message with initial countdown', () => {
    const endsAt = new Date(Date.now() + 2 * 3_600_000 + 30 * 60_000).toISOString() // 2h 30m from now
    render(<ElevationBanner endsAt={endsAt} onEndEarly={vi.fn()} />)

    expect(screen.getByText(/elevated session active/i)).toBeInTheDocument()
    expect(screen.getByText(/all actions logged as elevated/i)).toBeInTheDocument()
    expect(screen.getByText(/^2h 30m/)).toBeInTheDocument()
  })

  it('ticks the countdown down as time advances', () => {
    const endsAt = new Date(Date.now() + 60_000).toISOString() // 1 minute from now
    render(<ElevationBanner endsAt={endsAt} onEndEarly={vi.fn()} />)

    expect(screen.getByText(/^0h 1m/)).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(30_000) }) // advance 30s
    expect(screen.getByText(/^0h 0m 3[01]s$/)).toBeInTheDocument()
  })

  it('shows "Expired" once endsAt has passed', () => {
    const endsAt = new Date(Date.now() + 500).toISOString() // 0.5s from now
    render(<ElevationBanner endsAt={endsAt} onEndEarly={vi.fn()} />)

    act(() => { vi.advanceTimersByTime(1_000) }) // now past endsAt
    expect(screen.getByText('Expired')).toBeInTheDocument()
  })

  it('fires onEndEarly when the "End early" button is clicked', async () => {
    const onEndEarly = vi.fn()
    const endsAt = new Date(Date.now() + 3_600_000).toISOString()
    // userEvent needs real timers to drive its internal async delays
    vi.useRealTimers()
    const user = userEvent.setup()
    render(<ElevationBanner endsAt={endsAt} onEndEarly={onEndEarly} />)

    await user.click(screen.getByRole('button', { name: /end early/i }))
    expect(onEndEarly).toHaveBeenCalledTimes(1)
  })
})
