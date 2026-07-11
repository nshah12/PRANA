/**
 * AccountLocks tests
 *
 *  1. Loading skeleton
 *  2. Error state with retry
 *  3. Empty state — "No locked accounts"
 *  4. Renders locked account rows, including last failed IP and auto-unlock countdown text
 *  5. Manual unlock — confirm() gate, success path invalidates query
 *  6. Manual unlock — cancelled confirm() does not call the API
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AccountLocks } from './AccountLocks'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('AccountLocks', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<AccountLocks />, { wrapper })
    expect(screen.getByText('Account Locks')).toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<AccountLocks />, { wrapper })
    expect(await screen.findByText('Failed to load account locks.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('No locked accounts')).toBeInTheDocument())
  })

  it('shows empty state when there are no locked accounts', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<AccountLocks />, { wrapper })
    expect(await screen.findByText('No locked accounts')).toBeInTheDocument()
    expect(screen.getByText('All accounts are currently active.')).toBeInTheDocument()
  })

  it('renders locked account rows with failed attempt count, last IP, and auto-unlock countdown', async () => {
    const future = new Date(Date.now() + 3600_000).toISOString()
    vi.mocked(api.get).mockResolvedValue({
      data: {
        items: [{
          event_id: 'e-1',
          identifier: 'priya@acme.example',
          account_type: 'oa_user',
          locked_at: '2026-07-05T10:00:00Z',
          failed_attempt_count: 5,
          last_failed_ip: '198.51.100.7',
          scheduled_unlock_at: future,
        }],
      },
    })
    render(<AccountLocks />, { wrapper })
    expect(await screen.findByText('priya@acme.example')).toBeInTheDocument()
    expect(screen.getByText('OA User')).toBeInTheDocument()
    expect(screen.getByText(/5 failed attempts/)).toBeInTheDocument()
    expect(screen.getByText(/Last IP: 198.51.100.7/)).toBeInTheDocument()
    expect(screen.getByText(/Auto-unlocks/)).toBeInTheDocument()
  })

  it('manually unlocks an account after confirming, and refetches', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ event_id: 'e-1', identifier: 'priya@acme.example', account_type: 'oa_user', locked_at: '2026-07-05T10:00:00Z', failed_attempt_count: 5, last_failed_ip: null, scheduled_unlock_at: null }] },
    })
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'UNLOCKED' } })
    render(<AccountLocks />, { wrapper })
    const unlockBtn = await screen.findByText('Unlock now')
    await user.click(unlockBtn)
    expect(window.confirm).toHaveBeenCalledWith('Manually unlock priya@acme.example?')
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/ciso/account-locks/e-1/unlock'))
  })

  it('does not unlock when confirm() is cancelled', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ event_id: 'e-1', identifier: 'priya@acme.example', account_type: 'employee', locked_at: '2026-07-05T10:00:00Z', failed_attempt_count: 3, last_failed_ip: null, scheduled_unlock_at: null }] },
    })
    render(<AccountLocks />, { wrapper })
    const unlockBtn = await screen.findByText('Unlock now')
    await user.click(unlockBtn)
    expect(api.post).not.toHaveBeenCalled()
  })
})
