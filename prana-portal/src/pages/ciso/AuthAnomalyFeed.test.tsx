/**
 * AuthAnomalyFeed tests
 *
 *  1. Loading state — "Loading…" text shown while fetching
 *  2. Empty state — "No auth anomalies detected."
 *  3. Renders anomaly cards with the raw IP address (CISO-only privileged shape —
 *     employees never see raw IP; this view must show the full IP)
 *  4. Force-logout: confirm() gate, success path invalidates the query
 *  5. Force-logout: cancelled confirm() does not call the API
 *  6. Manual refresh button re-triggers the query
 *  7. No force-logout button when the anomaly has no session_id
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AuthAnomalyFeed } from './AuthAnomalyFeed'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('AuthAnomalyFeed', () => {
  it('shows the loading text while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<AuthAnomalyFeed />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows empty state when there are no auth anomalies', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { anomalies: [] } })
    render(<AuthAnomalyFeed />, { wrapper })
    expect(await screen.findByText('No auth anomalies detected.')).toBeInTheDocument()
  })

  it('renders anomaly cards with the full raw IP address visible (CISO-privileged shape)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        anomalies: [{
          event_id: 'ev-1',
          anomaly_type: 'IMPOSSIBLE_TRAVEL',
          severity: 'HIGH',
          description: 'Login from two countries within 10 minutes',
          ip_address: '203.0.113.9',
          detected_at: '2026-07-05T08:00:00Z',
          session_id: 'sess-1',
        }],
      },
    })
    render(<AuthAnomalyFeed />, { wrapper })
    expect(await screen.findByText('IMPOSSIBLE TRAVEL')).toBeInTheDocument()
    expect(screen.getByText('Login from two countries within 10 minutes')).toBeInTheDocument()
    expect(screen.getByText('IP: 203.0.113.9')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  it('force-logs-out a session after confirming', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(api.get).mockResolvedValue({
      data: { anomalies: [{ event_id: 'ev-1', anomaly_type: 'X', severity: 'HIGH', description: 'd', ip_address: '1.2.3.4', detected_at: '2026-07-05T08:00:00Z', session_id: 'sess-1' }] },
    })
    vi.mocked(api.post).mockResolvedValue({ data: {} })
    render(<AuthAnomalyFeed />, { wrapper })
    const logoutBtn = await screen.findByText('Force logout')
    await user.click(logoutBtn)
    expect(window.confirm).toHaveBeenCalledWith('Force logout this session?')
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/sessions/sess-1/revoke'))
  })

  it('does not force logout when confirm() is cancelled', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    vi.mocked(api.get).mockResolvedValue({
      data: { anomalies: [{ event_id: 'ev-1', anomaly_type: 'X', severity: 'AMBER', description: 'd', ip_address: '1.2.3.4', detected_at: '2026-07-05T08:00:00Z', session_id: 'sess-1' }] },
    })
    render(<AuthAnomalyFeed />, { wrapper })
    const logoutBtn = await screen.findByText('Force logout')
    await user.click(logoutBtn)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not render a force-logout button when there is no session_id', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { anomalies: [{ event_id: 'ev-2', anomaly_type: 'X', severity: 'AMBER', description: 'd', ip_address: '1.2.3.4', detected_at: '2026-07-05T08:00:00Z', session_id: null }] },
    })
    render(<AuthAnomalyFeed />, { wrapper })
    await screen.findByText('X')
    expect(screen.queryByText('Force logout')).not.toBeInTheDocument()
  })

  it('manually refreshes the anomaly feed via the refresh button', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { anomalies: [] } })
    render(<AuthAnomalyFeed />, { wrapper })
    await screen.findByText('No auth anomalies detected.')
    const callsBefore = vi.mocked(api.get).mock.calls.length
    await user.click(screen.getByText('Refresh'))
    await waitFor(() => expect(vi.mocked(api.get).mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
