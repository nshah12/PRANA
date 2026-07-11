/**
 * ComplianceExport tests
 *
 * This page has no useQuery — it's a static list of quick-report buttons plus
 * a custom-report form. Contract under test:
 *  1. Renders title, quick report list, custom report section
 *  2. Clicking a quick-report download button calls GET /v1/chro/reports/{id} with blob responseType
 *  3. Button shows "Generating…" while in-flight, reverts to "Download PDF" after
 *  4. Only the clicked button shows the generating state — others stay normal
 *  5. Download still completes (button resets) even if the request rejects
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { ComplianceExport } from './ComplianceExport'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom does not implement createObjectURL/revokeObjectURL
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  URL.revokeObjectURL = vi.fn()
})

describe('ComplianceExport', () => {
  it('renders title, quick reports, and custom report section', () => {
    render(<ComplianceExport />, { wrapper })
    expect(screen.getByText('Compliance Export')).toBeInTheDocument()
    expect(screen.getByText('Quick reports')).toBeInTheDocument()
    expect(screen.getByText('Vault Completeness Summary')).toBeInTheDocument()
    expect(screen.getByText('Form-16 Coverage')).toBeInTheDocument()
    expect(screen.getByText('Salary Slip Gap Report')).toBeInTheDocument()
    expect(screen.getByText('Statutory Compliance Matrix')).toBeInTheDocument()
    expect(screen.getByText('Custom report')).toBeInTheDocument()
    expect(screen.getByText('Select date range and categories for a custom compliance export.')).toBeInTheDocument()
  })

  it('downloads a quick report and calls the correct endpoint with blob responseType', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: new Blob(['pdf-bytes']) })
    render(<ComplianceExport />, { wrapper })

    const row = screen.getByText('Form-16 Coverage').closest('div')!
    const btn = row.querySelector('button')!
    await user.click(btn)

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/v1/chro/reports/form16_coverage', { responseType: 'blob' })
    )
  })

  it('shows "Generating…" only on the clicked button while in-flight, others unaffected', async () => {
    const user = userEvent.setup()
    let resolveFn: (v: any) => void
    mockGet.mockReturnValue(new Promise(res => { resolveFn = res }))
    render(<ComplianceExport />, { wrapper })

    const row = screen.getByText('Salary Slip Gap Report').closest('div')!
    const btn = row.querySelector('button')!
    user.click(btn)

    await waitFor(() => expect(within(row).getByText('Generating…')).toBeInTheDocument())

    // Other rows still show the normal label
    const otherRow = screen.getByText('Form-16 Coverage').closest('div')!
    expect(within(otherRow).getByText('Download PDF')).toBeInTheDocument()

    resolveFn!({ data: new Blob(['x']) })
    await waitFor(() => expect(within(row).getByText('Download PDF')).toBeInTheDocument())
  })

  it('resets generating state and surfaces an error message when the request fails', async () => {
    // BUG: downloadReport() in ComplianceExport.tsx had no catch — a failed
    // request became an unhandled promise rejection with zero user-facing
    // feedback (violates FRONTEND rule: error state must never be silent).
    // Fixed by adding a catch that sets a per-report error message rendered
    // via tError(), and asserting it here.
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network down'))
    render(<ComplianceExport />, { wrapper })

    const row = screen.getByText('Statutory Compliance Matrix').closest('div')!
    const btn = row.querySelector('button')!
    await user.click(btn)

    await waitFor(() => expect(within(row).getByText('Download PDF')).toBeInTheDocument())
    await screen.findByText('Failed to generate report. Please try again.')
  })
})
