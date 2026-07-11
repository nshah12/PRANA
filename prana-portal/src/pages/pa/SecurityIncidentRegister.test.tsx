import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SecurityIncidentRegister } from './SecurityIncidentRegister'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  items: [
    {
      incident_id: 'sinc-1', severity: 'P0', status: 'OPEN', incident_type: 'DATA_BREACH',
      title: 'Suspected credential leak', description: 'Multiple failed logins from foreign IP',
      tenant_id: 'tenant-uuid-1234', created_at: '2026-07-01T10:00:00Z',
      sla_deadline: null, assigned_role: 'CISO', resolution_note: null, escalated_at: null,
    },
    {
      incident_id: 'sinc-2', severity: 'P2', status: 'RESOLVED', incident_type: 'SLA_BREACH',
      title: 'Digest delayed', description: null,
      tenant_id: null, created_at: '2026-07-02T10:00:00Z',
      sla_deadline: null, assigned_role: null, resolution_note: 'Fixed queue backlog', escalated_at: null,
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('SecurityIncidentRegister', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<SecurityIncidentRegister />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state with retry on failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load security incidents.')).toBeInTheDocument())
  })

  it('shows empty state when no incidents match', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('No incidents match this filter')).toBeInTheDocument())
  })

  it('renders incident rows with severity and status', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Suspected credential leak')).toBeInTheDocument())
    expect(screen.getByText('Digest delayed')).toBeInTheDocument()
    expect(screen.getByText(/Fixed queue backlog/)).toBeInTheDocument()
  })

  it('escalates an open incident', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Suspected credential leak')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /escalate/i }))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/security-incidents/sinc-1/escalate', {}))
  })

  it('resolves an incident by entering a note and confirming', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Suspected credential leak')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^resolve$/i }))
    const textarea = screen.getByPlaceholderText(/resolution/i)
    await user.type(textarea, 'Reset compromised credentials')
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/admin/security-incidents/sinc-1/resolve',
      { resolution_note: 'Reset compromised credentials' },
    ))
  })

  it('filters by tenant id input', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<SecurityIncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Suspected credential leak')).toBeInTheDocument())
    const tenantInput = screen.getByPlaceholderText('Filter by tenant UUID…')
    await user.type(tenantInput, 'tenant-uuid-1234')
    await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith(expect.stringContaining('tenant_id=tenant-uuid-1234')))
  })
})
