/**
 * StatutoryCompliance tests
 *
 * Contract under test (GET /v1/chro/statutory-coverage):
 *  1. Loading skeleton while fetching
 *  2. Error state with retry button on failure
 *  3. Summary bar (active employees, current FY, HIGH gap count) renders from data
 *  4. Overall risk badge renders with correct severity styling
 *  5. Per-act cards render obligation, coverage bar, gap-count copy
 *  6. "as of" timestamp renders when present
 *  7. Retry re-invokes the query
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { StatutoryCompliance } from './StatutoryCompliance'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

const MOCK = {
  overall_risk: 'MEDIUM',
  active_employees: 480,
  current_fy: 'FY26',
  as_of: '2026-07-01T10:00:00Z',
  acts: [
    {
      act: 'EPF Act 1952',
      section: 'Sec 6',
      obligation: 'PF contribution filing',
      period: 'Jun 2026',
      deadline: '15 Jul 2026',
      severity: 'HIGH',
      compliant_employees: 400,
      total_employees: 480,
      coverage_pct: 83,
      gap_count: 80,
    },
    {
      act: 'Income Tax Act',
      section: 'Income Tax Act',
      obligation: 'Form 16 issuance',
      period: 'FY25',
      deadline: '31 May 2026',
      severity: 'LOW',
      compliant_employees: 480,
      total_employees: 480,
      coverage_pct: 100,
      gap_count: 0,
    },
  ],
}

describe('StatutoryCompliance', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<StatutoryCompliance />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders title and subtitle', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<StatutoryCompliance />, { wrapper })
    expect(screen.getByText('Statutory Compliance Coverage')).toBeInTheDocument()
    expect(screen.getByText(
      'Per-Act document coverage — auditable by Labour Inspector, TDS Auditor, EPFO Officer, Internal CA'
    )).toBeInTheDocument()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('Failed to load statutory coverage.')
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('re-invokes the query when retry is clicked', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network'))
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('Failed to load statutory coverage.')

    mockGet.mockResolvedValueOnce({ data: MOCK })
    await user.click(screen.getByRole('button', { name: /retry/i }))
    await screen.findByText('PF contribution filing')
  })

  it('renders the summary bar with active employees, FY, and HIGH gap count', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('480')
    expect(screen.getByText('Active employees')).toBeInTheDocument()
    expect(screen.getByText('FY26')).toBeInTheDocument()
    expect(screen.getByText('Current financial year')).toBeInTheDocument()
    // exactly 1 HIGH-severity act in MOCK
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('Acts with HIGH coverage gap')).toBeInTheDocument()
  })

  it('renders the overall risk badge', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('MEDIUM overall risk')
  })

  it('renders per-act cards with obligation, section, coverage, and gap copy', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('PF contribution filing')
    expect(screen.getByText('Form 16 issuance')).toBeInTheDocument()
    expect(screen.getByText('Sec 6')).toBeInTheDocument()
    expect(screen.getByText('400 of 480 employees compliant')).toBeInTheDocument()
    expect(screen.getByText('83%')).toBeInTheDocument()
    expect(screen.getByText(/80 employees missing/)).toBeInTheDocument()
  })

  it('does not show gap copy for a fully compliant act', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('Form 16 issuance')
    // Form 16 issuance card (gap_count: 0) must not render "X employees missing"
    const card = screen.getByText('Form 16 issuance').closest<HTMLElement>('div.bg-white')!
    expect(within(card).queryByText(/employees missing/)).not.toBeInTheDocument()
  })

  it('renders the "as of" IST timestamp when present', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<StatutoryCompliance />, { wrapper })
    await screen.findByText('PF contribution filing')
    expect(screen.getByText(/As of .* IST/)).toBeInTheDocument()
  })
})
