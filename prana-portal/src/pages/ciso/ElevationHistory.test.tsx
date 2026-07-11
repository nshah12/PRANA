/**
 * ElevationHistory tests
 *
 *  1. Loading skeleton
 *  2. Error state with retry
 *  3. Empty state — "No elevation history"
 *  4. Renders elevation rows with requestor/approver/status
 *  5. Pagination
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ElevationHistory } from './ElevationHistory'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('ElevationHistory', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<ElevationHistory />, { wrapper })
    expect(screen.getByText('Elevation History')).toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<ElevationHistory />, { wrapper })
    expect(await screen.findByText('Failed to load elevation history.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('No elevation history')).toBeInTheDocument())
  })

  it('shows empty state when there is no elevation history', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    render(<ElevationHistory />, { wrapper })
    expect(await screen.findByText('No elevation history')).toBeInTheDocument()
    expect(screen.getByText('No elevation requests have been made yet.')).toBeInTheDocument()
  })

  it('renders elevation rows with requestor, approver, reason, duration, and status', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{
          elevation_id: 'el-1',
          requestor_name: 'Ravi Kumar',
          requestor_email: 'ravi@acme.example',
          approver_name: 'Priya Sharma',
          reason: 'Payroll correction',
          duration_hours: 4,
          status: 'APPROVED',
          requested_at: '2026-07-05T08:00:00Z',
          expires_at: '2026-07-05T12:00:00Z',
        }],
      },
    })
    render(<ElevationHistory />, { wrapper })
    expect(await screen.findByText('Ravi Kumar')).toBeInTheDocument()
    expect(screen.getByText('ravi@acme.example')).toBeInTheDocument()
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument()
    expect(screen.getByText('Payroll correction')).toBeInTheDocument()
    expect(screen.getByText('4h')).toBeInTheDocument()
    expect(screen.getByText('APPROVED')).toBeInTheDocument()
  })

  it('shows dashes for missing optional fields', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{ elevation_id: 'el-2', requestor_name: null, approver_name: null, reason: null, duration_hours: null, status: 'PENDING', requested_at: '2026-07-05T08:00:00Z', expires_at: null }],
      },
    })
    render(<ElevationHistory />, { wrapper })
    expect(await screen.findByText('PENDING')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('paginates to the next page', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 120, items: [{ elevation_id: 'el-1', requestor_name: 'Ravi', approver_name: 'Priya', reason: 'x', duration_hours: 2, status: 'ACTIVE', requested_at: '2026-07-05T08:00:00Z', expires_at: '2026-07-05T10:00:00Z' }] },
    })
    render(<ElevationHistory />, { wrapper })
    await screen.findByText('Page 1 of 3')
    await user.click(screen.getByText('Next'))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/elevations', { params: { offset: 50, limit: 50 } }))
  })
})
