/**
 * ComplianceCalendar tests
 *
 * Contract under test (GET /v1/chro/compliance):
 *  1. Renders title/subtitle always
 *  2. Loading skeleton while fetching
 *  3. Error state with retry button on failure
 *  4. Overdue badge shown only when data.overdue > 0
 *  5. Table rows render obligation, deadline, coverage, status
 *  6. Empty state row when data.items is empty
 *  7. "Alert operator" CTA only on overdue rows
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ComplianceCalendar } from './ComplianceCalendar'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const FUTURE = new Date(Date.now() + 10 * 86_400_000).toISOString()
const PAST = new Date(Date.now() - 3 * 86_400_000).toISOString()

const MOCK = {
  overdue: 1,
  total: 2,
  items: [
    {
      obligation_id: 'ob-1',
      obligation_name: 'PF ECR filing',
      statutory_ref: 'EPF Act 1952',
      period: 'Jun 2026',
      deadline: FUTURE,
      is_overdue: false,
      total_employees: 100,
      completion_pct: 92,
      status: 'IN_PROGRESS',
    },
    {
      obligation_id: 'ob-2',
      obligation_name: 'TDS return Q1',
      statutory_ref: 'Income Tax Act',
      period: 'Q1 FY26',
      deadline: PAST,
      is_overdue: true,
      total_employees: 100,
      completion_pct: 40,
      status: 'OVERDUE',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('ComplianceCalendar', () => {
  it('renders title and subtitle', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<ComplianceCalendar />, { wrapper })
    expect(screen.getByText('Compliance Calendar')).toBeInTheDocument()
    expect(screen.getByText('Statutory deadlines — Labour law, DPDP Act, Income Tax Act')).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<ComplianceCalendar />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText('Failed to load compliance calendar.')).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows overdue badge only when overdue count > 0', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() => expect(screen.getByText('1 overdue')).toBeInTheDocument())
    expect(screen.getByText('2 obligations')).toBeInTheDocument()
  })

  it('does not show overdue badge when overdue is 0', async () => {
    // Must also flip each item's is_overdue — the per-row badge (line 91 of the
    // component) is driven by item.is_overdue independently of the aggregate
    // data.overdue count, so reusing MOCK's items (one of which is_overdue: true)
    // would still render a row-level "Xd overdue" badge.
    mockGet.mockResolvedValue({
      data: { ...MOCK, overdue: 0, items: MOCK.items.map(i => ({ ...i, is_overdue: false })) },
    })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() => expect(screen.getByText('2 obligations')).toBeInTheDocument())
    expect(screen.queryByText(/overdue$/)).not.toBeInTheDocument()
  })

  it('renders table rows with obligation name, statutory ref and status', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() => expect(screen.getByText('PF ECR filing')).toBeInTheDocument())
    expect(screen.getByText('EPF Act 1952')).toBeInTheDocument()
    expect(screen.getByText('TDS return Q1')).toBeInTheDocument()
    expect(screen.getByText('IN_PROGRESS')).toBeInTheDocument()
    expect(screen.getByText('OVERDUE')).toBeInTheDocument()
  })

  it('shows "Alert operator" CTA only on overdue rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() => expect(screen.getByText('PF ECR filing')).toBeInTheDocument())
    const alertButtons = screen.getAllByRole('button', { name: /alert operator/i })
    expect(alertButtons).toHaveLength(1)
  })

  it('renders empty-state row when there are no items', async () => {
    mockGet.mockResolvedValue({ data: { overdue: 0, total: 0, items: [] } })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/no compliance obligations configured/i)).toBeInTheDocument()
    )
  })

  it('calls the compliance endpoint', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ComplianceCalendar />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/v1/chro/compliance'))
  })
})
