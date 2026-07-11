import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AuditTrail } from './AuditTrail'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  events: [
    { event_type: 'DOC_UPLOADED', actor_id: 'actor-uuid-1234', tenant_name: 'Acme Ltd', created_at: '2026-07-01T10:00:00Z' },
    { event_type: 'TENANT_PROVISIONED', actor_id: 'actor-uuid-5678', tenant_name: null, created_at: '2026-07-02T10:00:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('AuditTrail', () => {
  it('shows loading text while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AuditTrail />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders audit event rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AuditTrail />, { wrapper })
    await waitFor(() => expect(screen.getByText('DOC_UPLOADED')).toBeInTheDocument())
    expect(screen.getByText('TENANT_PROVISIONED')).toBeInTheDocument()
    expect(screen.getByText('Acme Ltd')).toBeInTheDocument()
  })

  it('shows platform fallback for events with no tenant', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AuditTrail />, { wrapper })
    await waitFor(() => expect(screen.getByText('TENANT_PROVISIONED')).toBeInTheDocument())
    expect(screen.getByText('Platform')).toBeInTheDocument()
  })

  it('refetches with search text applied', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AuditTrail />, { wrapper })
    await waitFor(() => expect(screen.getByText('DOC_UPLOADED')).toBeInTheDocument())
    const search = screen.getByPlaceholderText(/search/i)
    await user.type(search, 'Acme')
    await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith('/admin/audit', {
      params: { q: 'Acme', event_type: undefined, offset: 0, limit: 100 },
    }))
  })

  it('exports audit as CSV via a blob download', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AuditTrail />, { wrapper })
    await waitFor(() => expect(screen.getByText('DOC_UPLOADED')).toBeInTheDocument())

    const blob = new Blob(['csv'], { type: 'text/csv' })
    mockGet.mockResolvedValueOnce({ data: blob })
    const origCreateObjectURL = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:mock')
    URL.revokeObjectURL = vi.fn()

    await user.click(screen.getByRole('button', { name: /export csv/i }))
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/admin/audit/export', { responseType: 'blob' }))

    URL.createObjectURL = origCreateObjectURL
    URL.revokeObjectURL = origRevoke
  })
})
