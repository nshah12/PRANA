/**
 * ConsentDashboard tests — DPDP Act 2023 compliance surface, be thorough.
 *
 * BUG FOUND: ConsentDashboard originally never destructured isLoading/isError from
 * useQuery, so it silently rendered '—' placeholders for both the loading state AND
 * any fetch failure — the "3 states" contract (loading/error/empty) from
 * .claude/rules/frontend.md was violated (no skeleton, no error message, no retry).
 * Fixed to match the sibling CFO pages' isLoading/isError/refetch pattern.
 *
 *  1. Loading skeleton shown while fetching (was: silently showed '—' stat cards)
 *  2. Error state with retry button on failure (was: silently showed '—' stat cards)
 *  3. Retry button refetches after failure
 *  4. Renders 4 stat cards with values
 *  5. Renders recent consent events with action badges
 *  6. Empty state — "No consent events yet."
 *  7. Export CSV mutation — success path, button re-enabled after
 *  8. Export CSV mutation — pending state disables button and shows "Exporting…"
 *  9. Export CSV mutation — error path does not crash the page
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ConsentDashboard } from './ConsentDashboard'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  granted: 412,
  pending: 38,
  refused: 5,
  coverage_pct: 91,
  events: [
    { employee_name: 'Anita Rao', action: 'GRANTED', occurred_at: '2026-06-20T09:00:00Z' },
    { employee_name: 'Vikram Shah', action: 'REFUSED', occurred_at: '2026-06-21T10:15:00Z' },
    { employee_name: 'Meera Nair', action: 'REVOKED', occurred_at: '2026-06-22T11:30:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('ConsentDashboard', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<ConsentDashboard />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<ConsentDashboard />, { wrapper })
    expect(await screen.findByText('Failed to load consent data.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('retry button refetches after failure', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network'))
    render(<ConsentDashboard />, { wrapper })
    await screen.findByRole('button', { name: 'Retry' })

    mockGet.mockResolvedValue({ data: MOCK })
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('412')).toBeInTheDocument()
  })

  it('renders 4 stat cards with correct values', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ConsentDashboard />, { wrapper })
    expect(await screen.findByText('412')).toBeInTheDocument()
    expect(screen.getByText('38')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()
  })

  it('renders recent consent events with action badges', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ConsentDashboard />, { wrapper })
    expect(await screen.findByText('Anita Rao')).toBeInTheDocument()
    expect(screen.getByText('Vikram Shah')).toBeInTheDocument()
    expect(screen.getByText('Meera Nair')).toBeInTheDocument()
    expect(screen.getByText('GRANTED')).toBeInTheDocument()
    expect(screen.getByText('REFUSED')).toBeInTheDocument()
    expect(screen.getByText('REVOKED')).toBeInTheDocument()
  })

  it('shows "No consent events yet." when events list is empty', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, events: [] } })
    render(<ConsentDashboard />, { wrapper })
    expect(await screen.findByText('No consent events yet.')).toBeInTheDocument()
  })

  it('export mutation shows "Exporting…" and disables button while pending', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockReturnValue(new Promise(() => {}))
    render(<ConsentDashboard />, { wrapper })

    await screen.findByText('412')
    const exportBtn = screen.getByRole('button', { name: 'Export CSV' })
    await user.click(exportBtn)

    expect(await screen.findByRole('button', { name: 'Exporting…' })).toBeDisabled()
  })

  it('export mutation success re-enables the button', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { message: 'CONSENT_EXPORT_READY' } })
    render(<ConsentDashboard />, { wrapper })

    await screen.findByText('412')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))

    expect(await screen.findByRole('button', { name: 'Export CSV' })).not.toBeDisabled()
    expect(mockPost).toHaveBeenCalledWith('/v1/org/consent/export', {})
  })

  it('export mutation error does not crash the page and re-enables the button', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockRejectedValue(new Error('network'))
    render(<ConsentDashboard />, { wrapper })

    await screen.findByText('412')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))

    expect(await screen.findByRole('button', { name: 'Export CSV' })).not.toBeDisabled()
    expect(screen.getByText('Consent Dashboard')).toBeInTheDocument()
  })
})
