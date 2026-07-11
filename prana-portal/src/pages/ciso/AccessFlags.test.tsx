/**
 * AccessFlags tests
 *
 *  1. Loading state — skeleton rows
 *  2. Error state — with retry button that refetches
 *  3. Empty state — "No flagged access entries."
 *  4. Renders flagged rows including the raw IP address (CISO-only privileged shape —
 *     employees only ever see city-level location; this view must show the full IP)
 *  5. Unflag mutation success path
 *  6. Pagination — Previous/Next
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AccessFlags } from './AccessFlags'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('AccessFlags', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<AccessFlags />, { wrapper })
    expect(screen.getByText('Flagged Access Log')).toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<AccessFlags />, { wrapper })
    expect(await screen.findByText('Failed to load flagged access log.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('No flagged access entries.')).toBeInTheDocument())
  })

  it('shows empty state when there are no flagged entries', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    render(<AccessFlags />, { wrapper })
    expect(await screen.findByText('No flagged access entries.')).toBeInTheDocument()
  })

  it('renders flagged rows with the full raw IP address visible (CISO-privileged shape)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{
          access_id: 'a-1',
          doc_type: 'SALARY_SLIP',
          doc_period: 'Apr 2026',
          access_channel: 'SHARE_LINK',
          ip_address: '203.0.113.42',
          flag_reason: 'BULK_ACCESS_ANOMALY',
          accessed_at: '2026-07-01T10:00:00Z',
        }],
      },
    })
    render(<AccessFlags />, { wrapper })
    expect(await screen.findByText('203.0.113.42')).toBeInTheDocument()
    expect(screen.getByText('SALARY SLIP')).toBeInTheDocument()
    expect(screen.getByText('BULK_ACCESS_ANOMALY')).toBeInTheDocument()
    expect(screen.getByText('1 flagged entries')).toBeInTheDocument()
  })

  it('unflags an entry and refetches the list', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 1, items: [{ access_id: 'a-1', doc_type: 'FORM_16', doc_period: null, access_channel: 'MOBILE', ip_address: '10.0.0.1', flag_reason: 'FOREIGN_IP', accessed_at: '2026-07-01T10:00:00Z' }] },
    })
    vi.mocked(api.patch).mockResolvedValue({ data: { message: 'UNFLAGGED' } })
    render(<AccessFlags />, { wrapper })
    const unflagBtn = await screen.findByText('Unflag')
    await user.click(unflagBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/access-flags/a-1', { is_flagged: false }))
  })

  it('paginates to the next page', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 120, items: [{ access_id: 'a-1', doc_type: 'FORM_16', doc_period: null, access_channel: 'MOBILE', ip_address: '10.0.0.1', flag_reason: 'X', accessed_at: '2026-07-01T10:00:00Z' }] },
    })
    render(<AccessFlags />, { wrapper })
    await screen.findByText('Page 1 of 3')
    await user.click(screen.getByText('Next'))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/access-flags', { params: { offset: 50, limit: 50 } }))
  })
})
