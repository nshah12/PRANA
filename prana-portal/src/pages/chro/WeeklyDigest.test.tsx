/**
 * WeeklyDigest tests — TDD RED → GREEN → REFACTOR
 *
 *  1. Renders DigestDatePicker always (not gated behind loading)
 *  2. Shows loading skeleton while fetching
 *  3. Shows error state with retry button on failure
 *  4. Renders 4 stat cards on success
 *  5. Renders docs-by-type bars when data present
 *  6. Renders vault-by-department bars when data present
 *  7. Shows exceptions alert when exceptions_open > 0
 *  8. Shows Send test button
 *  9. API URL includes from/to params
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { WeeklyDigest } from './WeeklyDigest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  from: '2026-06-12', to: '2026-06-19',
  docs_processed: 50, vault_completeness_pct: 84.0,
  exceptions_open: 2, alumni_self_served: 3, active_employees: 900,
  docs_by_type: [{ doc_type: 'SALARY_SLIP', count: 40 }],
  vault_by_department: [{ department: 'Engineering', score: 88.0 }],
}

beforeEach(() => vi.clearAllMocks())

describe('WeeklyDigest', () => {
  it('renders DigestDatePicker immediately (not gated behind loading)', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<WeeklyDigest />, { wrapper })
    expect(screen.getByRole('button', { name: /this week/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<WeeklyDigest />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders 4 stat cards on success', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('50')).toBeInTheDocument())
    expect(screen.getByText('84%')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders docs-by-type bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('SALARY SLIP')).toBeInTheDocument())
  })

  it('renders vault-by-department bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('Engineering')).toBeInTheDocument())
  })

  it('shows exceptions alert when exceptions_open > 0', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText(/2 open exception/i)).toBeInTheDocument())
  })

  it('shows Send test button', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<WeeklyDigest />, { wrapper })
    expect(screen.getByRole('button', { name: /send test/i })).toBeInTheDocument()
  })

  it('includes from/to in the API URL', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<WeeklyDigest />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toMatch(/from=\d{4}-\d{2}-\d{2}/)
    expect(url).toMatch(/to=\d{4}-\d{2}-\d{2}/)
  })
})
