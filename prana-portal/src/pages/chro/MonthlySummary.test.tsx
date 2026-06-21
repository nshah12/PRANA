/**
 * MonthlySummary tests — TDD RED → GREEN → REFACTOR
 *
 * Contract under test:
 *  1. Renders DigestDatePicker (date range control is present)
 *  2. Shows loading skeleton while query is in-flight
 *  3. Shows error state with retry button on query failure
 *  4. Renders 4 stat cards on success
 *  5. Renders vault-by-department bars when data present
 *  6. Renders docs-by-type bars when data present
 *  7. Shows export CTA at the bottom
 *  8. queryKey includes from + to so cache invalidates on range change
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { MonthlySummary } from './MonthlySummary'

// Mock the API module
vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const MOCK_DIGEST = {
  from: '2026-05-20',
  to:   '2026-06-19',
  docs_processed: 214,
  vault_completeness_pct: 87.2,
  exceptions_open: 3,
  alumni_self_served: 7,
  active_employees: 1997,
  docs_by_type: [
    { doc_type: 'SALARY_SLIP', count: 158 },
    { doc_type: 'FORM_16',     count: 56  },
  ],
  vault_by_department: [
    { department: 'Engineering', score: 93.0 },
    { department: 'Sales',       score: 74.0 },
  ],
}

beforeEach(() => { vi.clearAllMocks() })

describe('MonthlySummary', () => {
  it('renders DigestDatePicker', () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    // All 4 tabs from DigestDatePicker must be present
    expect(screen.getByRole('button', { name: /this week/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {})) // never resolves
    render(<MonthlySummary />, { wrapper })
    // animate-pulse skeleton must be in DOM
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network error'))
    render(<MonthlySummary />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders 4 stat cards with correct values on success', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    await waitFor(() => expect(screen.getByText('214')).toBeInTheDocument())
    expect(screen.getByText('87.2%')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('renders vault-by-department bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    await waitFor(() => expect(screen.getByText('Engineering')).toBeInTheDocument())
    expect(screen.getByText('Sales')).toBeInTheDocument()
  })

  it('renders docs-by-type bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    await waitFor(() => expect(screen.getByText('SALARY SLIP')).toBeInTheDocument())
    expect(screen.getByText('FORM 16')).toBeInTheDocument()
  })

  it('shows export CTA', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /export for townhall/i })).toBeInTheDocument()
    )
  })

  it('includes from and to in the API URL', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_DIGEST } })
    render(<MonthlySummary />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toMatch(/from=\d{4}-\d{2}-\d{2}/)
    expect(url).toMatch(/to=\d{4}-\d{2}-\d{2}/)
  })
})
