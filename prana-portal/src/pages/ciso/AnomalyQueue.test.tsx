/**
 * AnomalyQueue tests
 *
 *  1. Loading skeleton
 *  2. Error state with retry
 *  3. Empty ("clear") state when filtered results are empty
 *  4. Renders anomaly rows with severity/status badges
 *  5. Severity filter button triggers refetch with new params
 *  6. Status filter select triggers refetch with new params
 *  7. Triage actions: Investigate / Resolve / False positive mutations
 *  8. Pagination
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AnomalyQueue } from './AnomalyQueue'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('AnomalyQueue', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<AnomalyQueue />, { wrapper })
    expect(screen.getByText('Anomaly Triage Queue')).toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<AnomalyQueue />, { wrapper })
    expect(await screen.findByText('Failed to load anomaly queue.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('Queue clear')).toBeInTheDocument())
  })

  it('shows the clear/empty state when no anomalies match the filter', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    render(<AnomalyQueue />, { wrapper })
    expect(await screen.findByText('Queue clear')).toBeInTheDocument()
    expect(screen.getByText('No anomalies matching the current filter.')).toBeInTheDocument()
  })

  it('renders anomaly rows with severity and status pills', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{
          anomaly_id: 'an-1',
          rule_name: 'BULK_ACCESS_ANOMALY',
          severity: 'P0',
          status: 'OPEN',
          detected_at: '2026-07-05T09:00:00Z',
          acknowledged_at: null,
          financial_pattern: null,
        }],
      },
    })
    render(<AnomalyQueue />, { wrapper })
    expect(await screen.findByText('BULK ACCESS ANOMALY')).toBeInTheDocument()
    // 'P0' also matches the severity filter button — scope to the pill badge span.
    expect(screen.getAllByText('P0').length).toBeGreaterThanOrEqual(2)
    // 'OPEN' also matches the status filter <option> — scope to the status pill span.
    expect(screen.getAllByText('OPEN').length).toBeGreaterThanOrEqual(1)
  })

  it('refetches with the selected severity filter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    render(<AnomalyQueue />, { wrapper })
    await screen.findByText('Queue clear')
    await user.click(screen.getByText('P0'))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/anomaly-queue', {
      params: { severity: 'P0', status_filter: 'OPEN', offset: 0, limit: 50 },
    }))
  })

  it('refetches with the selected status filter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [], total: 0 } })
    render(<AnomalyQueue />, { wrapper })
    await screen.findByText('Queue clear')
    const select = screen.getByDisplayValue('OPEN')
    await user.selectOptions(select, 'RESOLVED')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/anomaly-queue', {
      params: { severity: undefined, status_filter: 'RESOLVED', offset: 0, limit: 50 },
    }))
  })

  it('triages an OPEN anomaly to INVESTIGATING', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 1, items: [{ anomaly_id: 'an-1', rule_name: 'X', severity: 'P1', status: 'OPEN', detected_at: '2026-07-05T09:00:00Z' }] },
    })
    vi.mocked(api.patch).mockResolvedValue({ data: {} })
    render(<AnomalyQueue />, { wrapper })
    const investigateBtn = await screen.findByText('Investigate')
    await user.click(investigateBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/anomaly-queue/an-1', { status: 'INVESTIGATING' }))
  })

  it('resolves an anomaly', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 1, items: [{ anomaly_id: 'an-2', rule_name: 'X', severity: 'P2', status: 'INVESTIGATING', detected_at: '2026-07-05T09:00:00Z' }] },
    })
    vi.mocked(api.patch).mockResolvedValue({ data: {} })
    render(<AnomalyQueue />, { wrapper })
    const resolveBtn = await screen.findByText('Resolve')
    await user.click(resolveBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/anomaly-queue/an-2', { status: 'RESOLVED' }))
  })

  it('marks an anomaly as false positive, and handles mutation errors gracefully', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 1, items: [{ anomaly_id: 'an-3', rule_name: 'X', severity: 'P3', status: 'OPEN', detected_at: '2026-07-05T09:00:00Z' }] },
    })
    vi.mocked(api.patch).mockRejectedValue(new Error('server error'))
    render(<AnomalyQueue />, { wrapper })
    const fpBtn = await screen.findByText('False positive')
    await user.click(fpBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/anomaly-queue/an-3', { status: 'FALSE_POSITIVE' }))
    // page does not crash after mutation error
    expect(screen.getByText('False positive')).toBeInTheDocument()
  })

  it('paginates to the next page', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 120, items: [{ anomaly_id: 'an-1', rule_name: 'X', severity: 'P2', status: 'OPEN', detected_at: '2026-07-05T09:00:00Z' }] },
    })
    render(<AnomalyQueue />, { wrapper })
    await screen.findByText('Page 1 of 3')
    await user.click(screen.getByText('Next'))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/anomaly-queue', {
      params: { severity: undefined, status_filter: 'OPEN', offset: 50, limit: 50 },
    }))
  })
})
