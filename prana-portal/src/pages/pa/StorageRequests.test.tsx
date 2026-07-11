import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { StorageRequests } from './StorageRequests'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = [
  {
    request_id: 'req-1', tenant_name: 'Acme Ltd', requested_gb: 200, current_gb: 50,
    requested_at: '2026-07-01T10:00:00Z', reason: 'Onboarding 2000 new employees', status: 'PENDING',
  },
  {
    request_id: 'req-2', tenant_name: 'Beta Inc', requested_gb: 100, current_gb: 80,
    requested_at: '2026-06-01T10:00:00Z', reason: null, status: 'APPROVED',
  },
]

beforeEach(() => vi.clearAllMocks())

describe('StorageRequests', () => {
  it('shows loading text while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<StorageRequests />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders storage requests with reason and pending count badge', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StorageRequests />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('Onboarding 2000 new employees')).toBeInTheDocument()
    expect(screen.getByText('1 pending')).toBeInTheDocument()
  })

  it('shows decision buttons only for PENDING requests', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StorageRequests />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.getByText('APPROVED')).toBeInTheDocument()
  })

  it('approves a pending storage request', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<StorageRequests />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/storage-requests/req-1/approve'))
  })

  it('rejects a pending storage request', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<StorageRequests />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^reject$/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/storage-requests/req-1/reject'))
  })
})
