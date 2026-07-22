/**
 * QuarterlyReport tests
 *
 * Static page — no useQuery. Contract under test:
 *  1. Renders title, description, and all 8 numbered content sections
 *  2. Clicking download calls GET /v1/chro/reports/quarterly with blob responseType
 *  3. Button shows "Generating…" while in-flight, reverts after resolve
 *  4. Button is disabled while generating
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { QuarterlyReport } from './QuarterlyReport'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  URL.revokeObjectURL = vi.fn()
})

describe('QuarterlyReport', () => {
  it('renders title, description, and the 8 report sections', () => {
    render(<QuarterlyReport />, { wrapper })
    expect(screen.getByText('Quarterly Report')).toBeInTheDocument()
    expect(screen.getByText(/Board-ready 8-page report/)).toBeInTheDocument()
    expect(screen.getByText('Contents')).toBeInTheDocument()
    ;[
      'Executive Summary', 'QoQ Vault Health Comparison', 'Department Breakdown',
      'Statutory Compliance Table', 'Exit Document Completeness',
      'Employer Brand Metrics', 'Risk & Recommendations', 'Data Residency Certificate',
    ].forEach(s => expect(screen.getByText(s)).toBeInTheDocument())
  })

  it('downloads the quarterly report calling the correct endpoint with blob responseType', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: new Blob(['pdf-bytes']) })
    render(<QuarterlyReport />, { wrapper })

    await user.click(screen.getByRole('button', { name: /download 8-page pdf/i }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/v1/chro/reports/quarterly', { responseType: 'blob' })
    )
  })

  it('shows "Generating…" and disables the button while in-flight, then reverts', async () => {
    const user = userEvent.setup()
    let resolveFn: (v: any) => void
    mockGet.mockReturnValue(new Promise(res => { resolveFn = res }))
    render(<QuarterlyReport />, { wrapper })

    const btn = screen.getByRole('button', { name: /download 8-page pdf/i })
    user.click(btn)

    await screen.findByText('Generating…')
    expect(screen.getByRole('button', { name: /generating/i })).toBeDisabled()

    resolveFn!({ data: new Blob(['x']) })
    await waitFor(() => expect(screen.getByRole('button', { name: /download 8-page pdf/i })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /download 8-page pdf/i })).not.toBeDisabled()
  })
})
