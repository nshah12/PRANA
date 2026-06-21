/**
 * PayrollIntelligence tests — TDD RED → GREEN → REFACTOR
 *
 *  1. Shows loading skeleton while fetching
 *  2. Shows error state with retry button on failure
 *  3. Renders trend chart heading on success
 *  4. Renders band distribution heading on success
 *  5. Shows integrity flags when present
 *  6. Shows no integrity flags section when empty
 *  7. Privacy: cohort disclaimer always visible
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PayrollIntelligence } from './PayrollIntelligence'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

// recharts uses ResizeObserver — stub it for jsdom
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  trend: [
    { month: 'Jan', total: 45000000 },
    { month: 'Feb', total: 46000000 },
  ],
  band_distribution: [
    { band: '5-10L', count: 320 },
    { band: '10-20L', count: 180 },
  ],
  integrity_flags: [],
}

beforeEach(() => vi.clearAllMocks())

describe('PayrollIntelligence', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<PayrollIntelligence />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<PayrollIntelligence />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders trend chart heading on success', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PayrollIntelligence />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/6-month payroll trend/i)).toBeInTheDocument()
    )
  })

  it('renders band distribution heading on success', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PayrollIntelligence />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/salary band distribution/i)).toBeInTheDocument()
    )
  })

  it('shows integrity flags when present', async () => {
    const mockWithFlags = { ...MOCK, integrity_flags: ['Ghost employee detected: emp-7721'] }
    mockGet.mockResolvedValue({ data: mockWithFlags })
    render(<PayrollIntelligence />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/ghost employee detected/i)).toBeInTheDocument()
    )
  })

  it('does not show integrity flags section when list is empty', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PayrollIntelligence />, { wrapper })
    await waitFor(() => expect(screen.getByText(/6-month payroll trend/i)).toBeInTheDocument())
    expect(screen.queryByText(/integrity flags/i)).not.toBeInTheDocument()
  })

  it('always shows cohort disclaimer', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<PayrollIntelligence />, { wrapper })
    expect(screen.getByText(/cohort min/i)).toBeInTheDocument()
  })
})
