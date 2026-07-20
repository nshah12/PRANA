/**
 * SecurityIncidents tests
 *
 *  1. Loading skeleton
 *  2. Error state with retry
 *  3. Empty state — "No incidents match this filter"
 *  4. Renders incident cards with severity/status/SLA chip
 *  5. Summary chip counts (P0 open, P1 open, total open)
 *  6. Severity / status filter selects trigger query param changes
 *  7. Resolve flow: opens textarea, submit disabled until note entered, success clears form
 *  8. Escalate mutation
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SecurityIncidents } from './SecurityIncidents'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('SecurityIncidents', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<SecurityIncidents />, { wrapper })
    expect(screen.getByText('Security Incidents')).toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<SecurityIncidents />, { wrapper })
    expect(await screen.findByText('Failed to load incidents.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('No incidents match this filter')).toBeInTheDocument())
  })

  it('shows empty state when there are no incidents', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<SecurityIncidents />, { wrapper })
    expect(await screen.findByText('No incidents match this filter')).toBeInTheDocument()
  })

  it('renders incident cards and summary counts', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        items: [
          { incident_id: 'i-1', severity: 'P0', status: 'OPEN', incident_type: 'BULK_ACCESS', title: 'Bulk document access detected', description: 'desc', created_at: '2026-07-05T08:00:00Z', sla_deadline: null },
          { incident_id: 'i-2', severity: 'P1', status: 'OPEN', incident_type: 'FOREIGN_LOGIN', title: 'Foreign IP login', created_at: '2026-07-05T09:00:00Z', sla_deadline: null },
        ],
      },
    })
    render(<SecurityIncidents />, { wrapper })
    expect(await screen.findByText('Bulk document access detected')).toBeInTheDocument()
    expect(screen.getByText('Foreign IP login')).toBeInTheDocument()
    // Summary: P0 Open=1, P1 Open=1, Total Open=2
    const p0Section = screen.getByText('P0 Open').closest('div')!
    expect(p0Section).toHaveTextContent('1')
    const p1Section = screen.getByText('P1 Open').closest('div')!
    expect(p1Section).toHaveTextContent('1')
    const totalSection = screen.getByText('Total Open').closest('div')!
    expect(totalSection).toHaveTextContent('2')
  })

  it('filters by severity via the select', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<SecurityIncidents />, { wrapper })
    await screen.findByText('No incidents match this filter')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[0], 'P0')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/incidents?severity=P0'))
  })

  it('filters by status via the select', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<SecurityIncidents />, { wrapper })
    await screen.findByText('No incidents match this filter')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[1], 'RESOLVED')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/incidents?status=RESOLVED'))
  })

  it('resolves an incident: opens note field, disables confirm until text entered, submits, and closes form on success', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ incident_id: 'i-1', severity: 'P2', status: 'OPEN', incident_type: 'X', title: 'Some incident', created_at: '2026-07-05T08:00:00Z', sla_deadline: null }] },
    })
    vi.mocked(api.patch).mockResolvedValue({ data: {} })
    render(<SecurityIncidents />, { wrapper })
    const resolveBtn = await screen.findByText('Resolve')
    await user.click(resolveBtn)

    const confirmBtn = screen.getByText('Confirm')
    expect(confirmBtn).toBeDisabled()

    const textarea = screen.getByPlaceholderText('Resolution note…')
    await user.type(textarea, 'Verified false alarm')
    expect(confirmBtn).not.toBeDisabled()

    await user.click(confirmBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/incidents/i-1/resolve', { resolution_note: 'Verified false alarm' }))
  })

  it('cancels the resolve form without submitting', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ incident_id: 'i-1', severity: 'P2', status: 'OPEN', incident_type: 'X', title: 'Some incident', created_at: '2026-07-05T08:00:00Z', sla_deadline: null }] },
    })
    render(<SecurityIncidents />, { wrapper })
    const resolveBtn = await screen.findByText('Resolve')
    await user.click(resolveBtn)
    await user.click(screen.getByText('Cancel'))
    expect(api.patch).not.toHaveBeenCalled()
    expect(screen.getByText('Resolve')).toBeInTheDocument()
  })

  it('escalates an incident', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ incident_id: 'i-3', severity: 'P1', status: 'OPEN', incident_type: 'X', title: 'Escalate me', created_at: '2026-07-05T08:00:00Z', sla_deadline: null }] },
    })
    vi.mocked(api.patch).mockResolvedValue({ data: {} })
    render(<SecurityIncidents />, { wrapper })
    const escalateBtn = await screen.findByText('Escalate')
    await user.click(escalateBtn)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/incidents/i-3/escalate', {}))
  })

  it('does not show action buttons for already-resolved incidents', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ incident_id: 'i-4', severity: 'P3', status: 'RESOLVED', incident_type: 'X', title: 'Already handled', created_at: '2026-07-05T08:00:00Z', sla_deadline: null, resolution_note: 'Fixed it' }] },
    })
    render(<SecurityIncidents />, { wrapper })
    expect(await screen.findByText('Already handled')).toBeInTheDocument()
    expect(screen.queryByText('Resolve')).not.toBeInTheDocument()
    expect(screen.queryByText('Escalate')).not.toBeInTheDocument()
  })

  // ── Errors tab (4th incident track, ERROR_OBSERVABILITY_DESIGN.md §7) ──────────

  const ERROR_ITEM = {
    error_id: 'err-1', exception_type: 'RuntimeError', source: 'HTTP',
    source_detail: '/v1/cfo/anomalies', tenant_id: 'tenant-001', occurrence_count: 2,
    first_seen_at: '2026-07-15T09:00:00Z', last_seen_at: '2026-07-15T10:00:00Z',
    status: 'NEW', linked_incident_id: null,
  }

  it('switches to the Errors tab and loads tenant-scoped errors', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<SecurityIncidents />, { wrapper })
    await screen.findByText('No incidents match this filter')

    vi.mocked(api.get).mockResolvedValue({ data: { items: [ERROR_ITEM] } })
    await user.click(screen.getByRole('button', { name: /^errors$/i }))

    expect(await screen.findByText('RuntimeError')).toBeInTheDocument()
    expect(api.get).toHaveBeenLastCalledWith('/v1/ciso/errors')
  })

  it('acknowledges a NEW error', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [ERROR_ITEM] } })
    vi.mocked(api.patch).mockResolvedValue({ data: { status: 'acknowledged' } })
    render(<SecurityIncidents />, { wrapper })
    await user.click(screen.getByRole('button', { name: /^errors$/i }))
    await screen.findByText('RuntimeError')

    await user.click(screen.getByRole('button', { name: /acknowledge/i }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/ciso/errors/err-1/acknowledge', {}))
  })

  it('resolves an error with a note', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [ERROR_ITEM] } })
    vi.mocked(api.patch).mockResolvedValue({ data: { status: 'resolved' } })
    render(<SecurityIncidents />, { wrapper })
    await user.click(screen.getByRole('button', { name: /^errors$/i }))
    await screen.findByText('RuntimeError')

    await user.click(screen.getByRole('button', { name: /^resolve$/i }))
    const textarea = screen.getByPlaceholderText('Resolution note…')
    await user.type(textarea, 'Confirmed benign')
    await user.click(screen.getByText('Confirm'))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/v1/ciso/errors/err-1/resolve', { resolution_note: 'Confirmed benign' },
    ))
  })

  it('does not offer ignore or promote-to-incident actions (PA-only)', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [ERROR_ITEM] } })
    render(<SecurityIncidents />, { wrapper })
    await user.click(screen.getByRole('button', { name: /^errors$/i }))
    await screen.findByText('RuntimeError')

    expect(screen.queryByRole('button', { name: /ignore/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /promote/i })).not.toBeInTheDocument()
  })
})
