/**
 * CfoDigest tests — TDD RED → GREEN → REFACTOR
 *
 *  1. Renders DigestDatePicker always (not gated behind loading)
 *  2. Shows loading skeleton while fetching
 *  3. Shows error state with retry button on failure
 *  4. Renders 4 stat cards on success
 *  5. Shows cost indicators block when estimates configured
 *  6. Cost indicators note must contain "estimate" (privacy contract)
 *  7. Renders financial doc compliance bars when data present
 *  8. Shows anomalies CTA when anomalies_pending > 0
 *  9. API URL includes from/to params
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CfoDigest } from './CfoDigest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  from: '2026-06-12', to: '2026-06-19',
  headcount: 1997, headcount_budget: 2050,
  exits: 22, joiners: 11, anomalies_pending: 3,
  cost_indicators: {
    avg_ctc_estimate: 1500000,
    replacement_cost_estimate: 150000,
    note: 'CFO-configured estimates — not extracted salary figures',
  },
  compliance_by_doc_type: { SALARY_SLIP: 1960, FORM_16: 1800 },
  headcount_by_department: [{ department: 'Engineering', count: 800 }],
}

beforeEach(() => vi.clearAllMocks())

describe('CfoDigest', () => {
  it('renders DigestDatePicker immediately (not gated behind loading)', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CfoDigest />, { wrapper })
    expect(screen.getByRole('button', { name: /this week/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CfoDigest />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<CfoDigest />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders 4 stat cards with correct values', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('1997')).toBeInTheDocument())
    expect(screen.getByText('22')).toBeInTheDocument()
    expect(screen.getByText('11')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('shows cost indicators block when estimates present', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText(/cost indicators/i)).toBeInTheDocument())
  })

  it('cost indicators note contains "estimate" — privacy contract', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/cfo-configured estimates/i)).toBeInTheDocument()
    )
  })

  it('renders financial doc compliance bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('SALARY SLIP')).toBeInTheDocument())
    expect(screen.getByText('FORM 16')).toBeInTheDocument()
  })

  it('shows anomalies CTA when anomalies_pending > 0', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText(/3 anomal/i)).toBeInTheDocument())
  })

  it('includes from/to in the API URL', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CfoDigest />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toMatch(/from=\d{4}-\d{2}-\d{2}/)
    expect(url).toMatch(/to=\d{4}-\d{2}-\d{2}/)
  })
})
