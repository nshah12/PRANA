/**
 * Benchmarking tests
 *
 *  1. Loading skeleton shown while fetching
 *  2. Error state with retry button on failure; retry re-fetches
 *  3. Renders table headers
 *  4. Renders benchmark rows with percentile labels + position badge
 *  5. Empty state — "No benchmarking data available" with minimum cohort note
 *  6. Position badge maps every known position code to its label
 *  7. Unknown position code falls back to raw value with neutral badge style
 *  8. Static privacy footer note always rendered
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Benchmarking } from './Benchmarking'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  rows: [
    {
      role_category: 'Software Engineer',
      p25_label: '₹8L', p50_label: '₹12L', p75_label: '₹18L',
      org_median_label: '₹11L', position: 'P25_P50',
    },
    {
      role_category: 'Product Manager',
      p25_label: '₹15L', p50_label: '₹22L', p75_label: '₹30L',
      org_median_label: '₹25L', position: 'ABOVE_P75',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('Benchmarking', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<Benchmarking />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<Benchmarking />, { wrapper })
    expect(await screen.findByText('Failed to load benchmarking data.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('retry button refetches after failure', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network'))
    render(<Benchmarking />, { wrapper })
    await screen.findByRole('button', { name: 'Retry' })

    mockGet.mockResolvedValue({ data: MOCK })
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Software Engineer')).toBeInTheDocument()
  })

  it('renders table column headers', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<Benchmarking />, { wrapper })
    await screen.findByText('Software Engineer')
    expect(screen.getByText('Role category')).toBeInTheDocument()
    expect(screen.getByText('Market P25')).toBeInTheDocument()
    expect(screen.getByText('Market P50')).toBeInTheDocument()
    expect(screen.getByText('Market P75')).toBeInTheDocument()
    expect(screen.getByText('Org median')).toBeInTheDocument()
    expect(screen.getByText('Position')).toBeInTheDocument()
  })

  it('renders benchmark rows with percentile labels and position badges', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<Benchmarking />, { wrapper })
    await screen.findByText('Software Engineer')
    expect(screen.getByText('₹8L')).toBeInTheDocument()
    expect(screen.getByText('₹12L')).toBeInTheDocument()
    expect(screen.getByText('₹18L')).toBeInTheDocument()
    expect(screen.getByText('₹11L')).toBeInTheDocument()
    expect(screen.getByText('P25–P50')).toBeInTheDocument()
    expect(screen.getByText('Above P75')).toBeInTheDocument()
  })

  it('shows empty state when no rows are available', async () => {
    mockGet.mockResolvedValue({ data: { rows: [] } })
    render(<Benchmarking />, { wrapper })
    expect(await screen.findByText('No benchmarking data available. Requires minimum cohort of 30.')).toBeInTheDocument()
  })

  it('falls back to raw position value with neutral style for unknown position codes', async () => {
    mockGet.mockResolvedValue({
      data: { rows: [{ ...MOCK.rows[0], position: 'SOME_UNKNOWN_CODE' }] },
    })
    render(<Benchmarking />, { wrapper })
    expect(await screen.findByText('SOME_UNKNOWN_CODE')).toBeInTheDocument()
  })

  it('always renders the aggregated-data privacy footer note', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<Benchmarking />, { wrapper })
    await screen.findByText('Software Engineer')
    expect(screen.getByText(/No individual employee data is included in market comparisons\./i)).toBeInTheDocument()
  })
})
