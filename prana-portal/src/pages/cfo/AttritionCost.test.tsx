/**
 * AttritionCost tests
 *
 *  1. Loading skeleton shown while fetching
 *  2. Error state with retry button on failure; retry calls refetch
 *  3. Renders 4 summary stat cards with values
 *  4. Falls back to '—' for missing numeric fields
 *  5. Renders monthly exits bar chart container (recharts, ResizeObserver polyfilled)
 *  6. Renders exit reasons with percentage bars
 *  7. Shows "no exit data" empty state when exit_reasons is empty
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AttritionCost } from './AttritionCost'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  exits_qtd: 18,
  attrition_rate_pct: 6.4,
  avg_tenure_months: 27,
  replacement_cost_label: 'Moderate',
  monthly_exits: [
    { month: 'Jan', exits: 4 },
    { month: 'Feb', exits: 6 },
  ],
  exit_reasons: [
    { reason: 'Better opportunity', pct: 45 },
    { reason: 'Relocation', pct: 20 },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('AttritionCost', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AttritionCost />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<AttritionCost />, { wrapper })
    expect(await screen.findByText('Failed to load attrition data.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('retry button calls refetch after failure', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network'))
    render(<AttritionCost />, { wrapper })
    await screen.findByRole('button', { name: 'Retry' })

    mockGet.mockResolvedValue({ data: MOCK })
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('18')).toBeInTheDocument()
  })

  it('renders 4 summary stat cards with correct values', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AttritionCost />, { wrapper })
    expect(await screen.findByText('18')).toBeInTheDocument()
    expect(screen.getByText('6.4%')).toBeInTheDocument()
    expect(screen.getByText('27m')).toBeInTheDocument()
    expect(screen.getByText('Moderate')).toBeInTheDocument()
  })

  it('falls back to em-dash for missing numeric fields', async () => {
    mockGet.mockResolvedValue({ data: {} })
    render(<AttritionCost />, { wrapper })
    await screen.findByText('Attrition Cost')
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBe(4)
  })

  it('renders exit reasons with percentage labels', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AttritionCost />, { wrapper })
    expect(await screen.findByText('Better opportunity')).toBeInTheDocument()
    expect(screen.getByText('Relocation')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('20%')).toBeInTheDocument()
  })

  it('shows "no exit data" empty state when exit_reasons is empty', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, exit_reasons: [] } })
    render(<AttritionCost />, { wrapper })
    expect(await screen.findByText('No exit data for this period.')).toBeInTheDocument()
  })

  it('renders section headings for charts', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AttritionCost />, { wrapper })
    expect(await screen.findByText('Monthly exits (rolling 12m)')).toBeInTheDocument()
    expect(screen.getByText('Exit reasons (category split)')).toBeInTheDocument()
  })
})
