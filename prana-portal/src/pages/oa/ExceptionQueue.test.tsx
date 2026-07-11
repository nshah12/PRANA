/**
 * ExceptionQueue tests
 *
 *  1. Loading state
 *  2. Empty state — no open exceptions
 *  3. Renders exception card fields; PAN field is always redacted (privacy contract)
 *  4. SLA breach banner + badge shown for items >= 24hr old
 *  5. Filter buttons narrow the visible list
 *  6. OA-Admin: quick-assign to top candidate calls resolve mutation
 *  7. OA-Admin: search & assign flow calls employee search then resolve mutation
 *  8. OA-Admin: dismiss calls dismiss mutation
 *  9. OA-Operator: sees admin-only note instead of action buttons, candidates disabled
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ExceptionQueue } from './ExceptionQueue'
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

function hoursAgoIso(h: number) {
  return new Date(Date.now() - h * 3_600_000).toISOString()
}

function makeException(overrides: Partial<any> = {}) {
  return {
    exception_id: 'ex-1',
    document_id: 'doc-1',
    doc_type: 'SALARY_SLIP',
    doc_period: 'Jun 2024',
    exception_type: 'MULTIPLE_CANDIDATES',
    extracted_fields: { name: 'Rahul Mehta', pan: 'ABCDE1234F' },
    candidate_matches: [
      { employee_uuid: 'emp-1', name: 'Rahul Mehta', emp_id: 'EMP001', confidence: 0.92 },
    ],
    status: 'OPEN',
    raised_at: hoursAgoIso(1),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('ExceptionQueue', () => {
  it('shows loading state while fetching', () => {
    setUser('oa_admin')
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<ExceptionQueue />, { wrapper })
    expect(screen.getByText('Loading exceptions…')).toBeInTheDocument()
  })

  it('shows empty state when there are no open exceptions', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { exceptions: [] } })
    render(<ExceptionQueue />, { wrapper })
    expect(await screen.findByText('No open exceptions')).toBeInTheDocument()
    expect(screen.getByText('All documents resolved — vault is clean')).toBeInTheDocument()
  })

  it('renders exception fields and always redacts PAN (privacy contract)', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { exceptions: [makeException()] } })
    render(<ExceptionQueue />, { wrapper })
    expect(await screen.findByText('[REDACTED]')).toBeInTheDocument()
    expect(screen.getAllByText('Rahul Mehta', { exact: false }).length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toContain('ABCDE1234F')
  })

  it('shows SLA breach banner and badge for exceptions older than 24 hours', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { exceptions: [makeException({ raised_at: hoursAgoIso(30) })] } })
    render(<ExceptionQueue />, { wrapper })
    expect(await screen.findByText(/have exceeded/)).toBeInTheDocument()
    expect(screen.getByText('SLA BREACH — 30hr')).toBeInTheDocument()
  })

  it('filters the list when a filter button is clicked', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({
      data: {
        exceptions: [
          makeException({ exception_id: 'ex-a', exception_type: 'NO_MATCH', extracted_fields: { name: 'A' } }),
          makeException({ exception_id: 'ex-b', exception_type: 'MULTIPLE_CANDIDATES', extracted_fields: { name: 'B' } }),
        ],
      },
    })
    render(<ExceptionQueue />, { wrapper })
    await screen.findByText('· A', { exact: false })
    expect(screen.getByText('· B', { exact: false })).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'No match' }))
    expect(screen.queryByText('· B', { exact: false })).not.toBeInTheDocument()
    expect(screen.getByText('· A', { exact: false })).toBeInTheDocument()
  })

  it('OA-Admin: quick-assigns to the top candidate', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { exceptions: [makeException()] } })
    mockPost.mockResolvedValue({ data: {} })
    render(<ExceptionQueue />, { wrapper })

    await screen.findByText('EMP001', { exact: false })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Assign to Rahul/ }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/v1/org/exceptions/ex-1/resolve', { employee_uuid: 'emp-1' },
    ))
  })

  it('OA-Admin: search & assign — searches employee master and assigns selection', async () => {
    setUser('oa_admin')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/employees/search')) {
        return Promise.resolve({ data: [{ employee_uuid: 'emp-9', name: 'Sunita Rao', emp_id: 'EMP009', confidence: 1 }] })
      }
      return Promise.resolve({ data: { exceptions: [makeException()] } })
    })
    mockPost.mockResolvedValue({ data: {} })
    render(<ExceptionQueue />, { wrapper })

    await screen.findByText('EMP001', { exact: false })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Search & Assign' }))
    await user.type(screen.getByPlaceholderText('Name, Emp ID, email…'), 'Sunita')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText(/Sunita Rao/)).toBeInTheDocument()
    const resultRow = screen.getByText(/Sunita Rao/).closest('button') as HTMLElement
    await user.click(resultRow)

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/v1/org/exceptions/ex-1/resolve', { employee_uuid: 'emp-9' },
    ))
  })

  it('OA-Admin: dismiss calls the dismiss mutation', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { exceptions: [makeException()] } })
    mockPost.mockResolvedValue({ data: {} })
    render(<ExceptionQueue />, { wrapper })

    await screen.findByText('EMP001', { exact: false })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/exceptions/ex-1/dismiss'))
  })

  it('OA-Operator: sees admin-only note, no action buttons, candidates disabled', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { exceptions: [makeException()] } })
    render(<ExceptionQueue />, { wrapper })

    await screen.findByText('EMP001', { exact: false })
    expect(screen.getByText('Identity resolution requires OA-Admin access. Contact your OA-Admin to assign this document.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
    const candidateBtn = screen.getByText('EMP001', { exact: false }).closest('button')
    expect(candidateBtn).toBeDisabled()
  })
})
