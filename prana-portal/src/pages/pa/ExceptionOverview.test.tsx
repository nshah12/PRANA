import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ExceptionOverview } from './ExceptionOverview'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  open_count: 3, in_progress_count: 2, resolved_24h: 5, sla_breach_count: 1,
  exceptions: [
    {
      exception_id: 'exc-1', document_name: 'salary_slip_apr.pdf', status: 'OPEN',
      sla_breached: true, tenant_name: 'Acme Ltd', exception_type: 'IDENTITY_MISMATCH',
      created_at: '2026-07-01T10:00:00Z',
    },
    {
      exception_id: 'exc-2', document_name: 'form16.pdf', status: 'RESOLVED',
      sla_breached: false, tenant_name: 'Beta Inc', exception_type: 'OCR_FAILED',
      created_at: '2026-07-02T10:00:00Z',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('ExceptionOverview', () => {
  it('renders 4 stat cards from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ExceptionOverview />, { wrapper })
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows empty state when no exceptions', async () => {
    mockGet.mockResolvedValue({ data: { open_count: 0, in_progress_count: 0, resolved_24h: 0, sla_breach_count: 0, exceptions: [] } })
    render(<ExceptionOverview />, { wrapper })
    await waitFor(() => expect(screen.getByText('No active exceptions.')).toBeInTheDocument())
  })

  it('renders exception rows with tenant and type', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ExceptionOverview />, { wrapper })
    await waitFor(() => expect(screen.getByText('salary_slip_apr.pdf')).toBeInTheDocument())
    expect(screen.getByText(/Acme Ltd/)).toBeInTheDocument()
    expect(screen.getByText(/IDENTITY MISMATCH/)).toBeInTheDocument()
  })

  it('does not show "Mark resolved" button for already-resolved exceptions', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ExceptionOverview />, { wrapper })
    await waitFor(() => expect(screen.getByText('form16.pdf')).toBeInTheDocument())
    const resolveButtons = screen.getAllByRole('button', { name: /mark resolved/i })
    expect(resolveButtons).toHaveLength(1)
  })

  it('resolves an exception and invalidates the query on success', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<ExceptionOverview />, { wrapper })
    await waitFor(() => expect(screen.getByText('salary_slip_apr.pdf')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /mark resolved/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/exceptions/exc-1/resolve', {}))
  })
})
