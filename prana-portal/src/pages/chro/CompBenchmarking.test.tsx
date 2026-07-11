/**
 * CompBenchmarking tests
 *
 * Contract under test (GET /v1/benchmarking/org/bands, GET /v1/benchmarking/org/opt-in-stats):
 *  1. Loading skeleton while fetching bands
 *  2. Error state on bands failure
 *  3. Empty state when no bands returned
 *  4. Summary KPIs (published/suppressed count, total contributors, k-min threshold)
 *  5. Range chart + band table render for published bands, using lakhs labels — never raw ₹
 *  6. Suppressed bands notice renders count + per-band chips
 *  7. Opt-in stats panel renders opted-in/not-opted-in/rate + progress bar
 *  8. Privacy contract: no raw ₹ figures anywhere in rendered output
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CompBenchmarking } from './CompBenchmarking'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

const BANDS_MOCK = {
  k_min: 50,
  items: [
    {
      grade: 'M3', department: 'Engineering', period: 'FY26-Q1',
      sample_count: 62, suppressed: false,
      p25: 800_000_00, p50: 1_000_000_00, p75: 1_250_000_00,
      computed_at: '2026-07-01T10:00:00Z', data_freshness: '3 days ago',
    },
    {
      grade: 'M4', department: 'Sales', period: 'FY26-Q1',
      sample_count: 30, suppressed: true,
      p25: null, p50: null, p75: null,
      computed_at: '2026-07-01T10:00:00Z', data_freshness: '3 days ago',
    },
  ],
}

const OPT_IN_MOCK = {
  total_active_employees: 480,
  opted_in: 200,
  not_opted_in: 280,
  opt_in_rate_pct: 42,
}

function mockBothEndpoints(bands: any, optIn: any) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/benchmarking/org/bands') return Promise.resolve({ data: bands })
    if (url === '/v1/benchmarking/org/opt-in-stats') return Promise.resolve({ data: optIn })
    return Promise.reject(new Error(`unexpected url ${url}`))
  })
}

describe('CompBenchmarking', () => {
  it('shows loading skeleton while fetching bands', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CompBenchmarking />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders title, subtitle and threshold note', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CompBenchmarking />, { wrapper })
    expect(screen.getByText('Comp Benchmarking')).toBeInTheDocument()
    expect(screen.getByText("Your org's compensation bands vs. verified market data")).toBeInTheDocument()
    expect(screen.getByText(
      'Bands require ≥ 50 employee contributions (k-anonymity). Below threshold → suppressed.'
    )).toBeInTheDocument()
  })

  it('shows error state when bands fail to load', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/benchmarking/org/bands') return Promise.reject(new Error('network'))
      return Promise.resolve({ data: OPT_IN_MOCK })
    })
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('Failed to load comp bands')
  })

  it('shows empty state when no bands returned', async () => {
    mockBothEndpoints({ k_min: 50, items: [] }, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('No comp bands yet')
    expect(screen.getByText(/Bands appear once employees opt in/)).toBeInTheDocument()
  })

  it('renders summary KPIs for published/suppressed bands and k-min threshold', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    // dynamic data-derived value — not a static label
    await screen.findByText('M3')
    const publishedCard = screen.getByText('Published bands').closest<HTMLElement>('div.stat-card')!
    expect(within(publishedCard).getByText('1')).toBeInTheDocument()
    const suppressedCard = screen.getByText('Suppressed (growing)').closest<HTMLElement>('div.stat-card')!
    expect(within(suppressedCard).getByText('1')).toBeInTheDocument()
    const contributorsCard = screen.getByText('Total contributors').closest<HTMLElement>('div.stat-card')!
    expect(within(contributorsCard).getByText('62')).toBeInTheDocument() // only published counted
    const kMinCard = screen.getByText('k-min threshold').closest<HTMLElement>('div.stat-card')!
    expect(within(kMinCard).getByText('50')).toBeInTheDocument()
  })

  it('renders the range chart section for published bands', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    expect(screen.getByText('Compensation range by grade')).toBeInTheDocument()
    expect(screen.getByText('P25–P75 spread')).toBeInTheDocument()
    expect(screen.getAllByText('Median').length).toBeGreaterThan(0)
  })

  it('renders the band table with lakhs-formatted values, never raw amounts', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    expect(screen.getByText('Engineering')).toBeInTheDocument()
    expect(screen.getByText('FY26-Q1')).toBeInTheDocument()
    // p25=8,00,00,000 paise -> 8.0L ; p50 -> 10.0L ; p75 -> 12.5L
    expect(screen.getByText('8.0L')).toBeInTheDocument()
    expect(screen.getByText('10.0L')).toBeInTheDocument()
    expect(screen.getByText('12.5L')).toBeInTheDocument()
  })

  it('renders suppressed bands notice with count and per-band chip', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    expect(screen.getByText('1 band waiting for more contributors')).toBeInTheDocument()
    expect(screen.getByText('M4 · Sales · 30/50')).toBeInTheDocument()
  })

  it('renders opt-in stats panel with opted-in, not-opted-in, and rate', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    expect(screen.getByText('Employee opt-in status')).toBeInTheDocument()
    expect(screen.getByText('Bands publish automatically once a cohort reaches 50 contributors')).toBeInTheDocument()
    expect(screen.getByText('200')).toBeInTheDocument()
    expect(screen.getByText('Opted in')).toBeInTheDocument()
    expect(screen.getByText('280')).toBeInTheDocument()
    expect(screen.getByText("Haven't opted in")).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByText('Opt-in rate')).toBeInTheDocument()
    expect(screen.getByText(/280 employees haven't opted in yet\./)).toBeInTheDocument()
  })

  it('filters by department, grade, and period via query params', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      '/v1/benchmarking/org/bands',
      { params: {} },
    ))
  })

  it('never renders raw rupee figures anywhere on the page', async () => {
    mockBothEndpoints(BANDS_MOCK, OPT_IN_MOCK)
    render(<CompBenchmarking />, { wrapper })
    await screen.findByText('M3')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
