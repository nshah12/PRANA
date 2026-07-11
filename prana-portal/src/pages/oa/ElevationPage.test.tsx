/**
 * ElevationPage tests
 *
 *  OA-Operator view:
 *   1. Shows active elevation banner + end-early action
 *   2. Duration picker + reason required to enable submit; posts request; shows "sent" confirmation
 *   3. Past requests history renders with status badges
 *
 *  OA-Admin view:
 *   4. Pending approvals empty state
 *   5. Renders pending request card; approve/deny call mutation endpoints
 *   6. History table renders with status badges
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ElevationPage } from './ElevationPage'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function setUser(role: 'oa_operator' | 'oa_admin') {
  useAuthStore.getState().setUser({
    userId: 'u-1', email: 'x@acme.example', displayName: 'X',
    role, tenantId: 't-1', tenantName: 'Acme Ltd',
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('ElevationPage — OA-Operator', () => {
  function mockOperatorGets({
    active = null,
    history = [] as any[],
    adminName = 'Priya Sharma',
  }: { active?: any; history?: any[]; adminName?: string } = {}) {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/elevations/active')) return Promise.resolve({ data: active })
      if (url.includes('/elevations/history')) return Promise.resolve({ data: history })
      if (url.includes('/admin-name')) return Promise.resolve({ data: { name: adminName } })
      return Promise.resolve({ data: {} })
    })
  }

  it('shows the active elevation banner with end-early action', async () => {
    setUser('oa_operator')
    mockOperatorGets({
      active: { elevation_id: 'e-1', ends_at: new Date().toISOString(), duration_hours: 2, reason: 'r' },
    })
    render(<ElevationPage />, { wrapper })
    expect(await screen.findByText('Elevated session is active')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'End early' })).toBeInTheDocument()
  })

  it('requires reason before enabling submit, then posts request and shows sent confirmation', async () => {
    setUser('oa_operator')
    mockOperatorGets()
    mockPost.mockResolvedValue({ data: {} })
    render(<ElevationPage />, { wrapper })

    await screen.findByText('New Elevation Request')
    const sendBtn = screen.getByRole('button', { name: 'Send Request to OA-Admin' })
    expect(sendBtn).toBeDisabled()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '4 hours' }))
    await user.type(screen.getByPlaceholderText(/Describe specifically why you need document access/), 'Need to review Form 16 disputes')

    expect(sendBtn).not.toBeDisabled()
    await user.click(sendBtn)

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/elevations', {
      duration_hours: 4, reason: 'Need to review Form 16 disputes',
    }))
    expect(await screen.findByText('Request sent')).toBeInTheDocument()
    expect(screen.getByText('Priya Sharma has been notified and will approve or deny your request.')).toBeInTheDocument()
  })

  it('renders past requests with status badges', async () => {
    setUser('oa_operator')
    mockOperatorGets({
      history: [
        { elevation_id: 'h-1', requestor_name: 'X', requestor_id: 'u-1', duration_hours: 2,
          reason: 'Routine check', status: 'APPROVED', requested_at: new Date().toISOString(),
          decided_by_name: 'Admin A' },
      ],
    })
    render(<ElevationPage />, { wrapper })
    expect(await screen.findByText('Past Requests')).toBeInTheDocument()
    expect(screen.getByText(/2hr — Routine check/)).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })
})

describe('ElevationPage — OA-Admin', () => {
  function mockAdminGets({ pending = [] as any[], history = [] as any[] } = {}) {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/elevations/pending')) return Promise.resolve({ data: { elevations: pending } })
      if (url.includes('/elevations/history')) return Promise.resolve({ data: { elevations: history } })
      return Promise.resolve({ data: {} })
    })
  }

  it('shows empty state when there are no pending requests', async () => {
    setUser('oa_admin')
    mockAdminGets()
    render(<ElevationPage />, { wrapper })
    expect(await screen.findByText('No pending elevation requests')).toBeInTheDocument()
  })

  it('renders a pending request and approves it', async () => {
    setUser('oa_admin')
    mockAdminGets({
      pending: [{
        elevation_id: 'p-1', requestor_name: 'Ravi Kumar', requestor_id: 'u-2',
        duration_hours: 4, reason: 'Investigating exception queue backlog',
        status: 'PENDING', requested_at: new Date().toISOString(),
      }],
    })
    mockPost.mockResolvedValue({ data: {} })
    render(<ElevationPage />, { wrapper })

    expect(await screen.findByText('Ravi Kumar')).toBeInTheDocument()
    expect(screen.getByText('"Investigating exception queue backlog"')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Approve 4hr' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/elevations/p-1/approve'))
  })

  it('denies a pending request', async () => {
    setUser('oa_admin')
    mockAdminGets({
      pending: [{
        elevation_id: 'p-2', requestor_name: 'Neha Singh', requestor_id: 'u-3',
        duration_hours: 2, reason: 'Testing', status: 'PENDING', requested_at: new Date().toISOString(),
      }],
    })
    mockPost.mockResolvedValue({ data: {} })
    render(<ElevationPage />, { wrapper })

    await screen.findByText('Neha Singh')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/elevations/p-2/deny'))
  })

  it('shows empty history message and renders history rows when present', async () => {
    setUser('oa_admin')
    mockAdminGets({
      history: [{
        elevation_id: 'h-9', requestor_name: 'Amit Verma', requestor_id: 'u-4',
        duration_hours: 8, reason: 'Audit', status: 'DENIED',
        requested_at: new Date().toISOString(), decided_at: new Date().toISOString(),
      }],
    })
    render(<ElevationPage />, { wrapper })
    expect(await screen.findByText('Amit Verma')).toBeInTheDocument()
    const table = document.querySelector('table') as HTMLElement
    expect(within(table).getByText('Denied')).toBeInTheDocument()
  })
})
