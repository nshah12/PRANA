/**
 * OaActivityAudit tests
 *
 *  1. Loading state — "Loading…" row shown while fetching
 *  2. Renders event rows with the raw IP address (CISO-only privileged shape —
 *     employees never see raw IP, only city-level; this view must show the full IP)
 *  3. Action type filter triggers refetch with new params
 *  4. Search input updates local state (client-side, not sent to API — documented as-is)
 *  5. Export PDF button triggers blob download flow
 *
 * NOTE: The component has no `isError` handling and no explicit "no events" empty
 * state — an empty `data.events` array simply renders zero <tr> rows (no blank-screen
 * crash, but no empty-state messaging either). This is a real gap relative to the
 * project's "never blank list" rule (frontend.md), but it is pre-existing UI behavior
 * outside a genuine bug in logic (wrong endpoint/field/mutation), so it is left as-is
 * per the "stay scoped to bugs you actually encounter" instruction and reported
 * separately rather than silently reshaping the component under a test-writing task.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { OaActivityAudit } from './OaActivityAudit'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('OaActivityAudit', () => {
  it('shows the loading row while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<OaActivityAudit />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders audit event rows with the full raw IP address visible (CISO-privileged shape)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        events: [{
          actor_name: 'Priya Sharma',
          actor_role: 'oa_admin',
          action_type: 'DOC_DELETE',
          resource_id: 'doc-123',
          ip_address: '192.0.2.55',
          created_at: '2026-07-05T08:00:00Z',
        }],
      },
    })
    render(<OaActivityAudit />, { wrapper })
    expect(await screen.findByText('Priya Sharma')).toBeInTheDocument()
    expect(screen.getByText('192.0.2.55')).toBeInTheDocument()
    // 'DOC DELETE' also appears as an <option> in the action-type filter select —
    // scope the assertion to the row's badge span specifically.
    expect(screen.getByText('DOC DELETE', { selector: 'span.badge' })).toBeInTheDocument()
  })

  it('refetches with the selected action type filter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { events: [] } })
    render(<OaActivityAudit />, { wrapper })
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    const select = screen.getByDisplayValue('ALL')
    await user.selectOptions(select, 'ELEVATION')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/oa-audit', {
      params: { action_type: 'ELEVATION', offset: 0, limit: 50 },
    }))
  })

  it('lets the user type into the search field', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { events: [] } })
    render(<OaActivityAudit />, { wrapper })
    const search = screen.getByPlaceholderText('Search by user or action…')
    await user.type(search, 'priya')
    expect(search).toHaveValue('priya')
  })

  it('exports a signed PDF via blob download on click', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/v1/ciso/oa-audit/export') {
        return Promise.resolve({ data: new Blob(['pdf-bytes']) })
      }
      return Promise.resolve({ data: { events: [] } })
    })
    const createObjectURL = vi.fn().mockReturnValue('blob:mock-url')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })

    render(<OaActivityAudit />, { wrapper })
    await user.click(screen.getByText('Export signed PDF'))

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/oa-audit/export', { responseType: 'blob' }))
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')

    vi.unstubAllGlobals()
  })
})
