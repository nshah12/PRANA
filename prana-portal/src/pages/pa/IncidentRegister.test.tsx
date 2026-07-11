import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { IncidentRegister } from './IncidentRegister'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  open_count: 2, p1_open: 1,
  incidents: [
    {
      incident_id: 'inc-1', severity: 'P1', status: 'OPEN', service_name: 'prana-api',
      title: 'API latency spike', detail: '5xx rate above threshold',
      detected_at: '2026-07-01T10:00:00Z', resolved_at: null, resolution_note: null,
    },
    {
      incident_id: 'inc-2', severity: 'P2', status: 'ACKNOWLEDGED', service_name: 'kafka',
      title: 'Consumer lag growing', detail: null,
      detected_at: '2026-07-02T10:00:00Z', resolved_at: null, resolution_note: null,
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('IncidentRegister', () => {
  it('shows loading text while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<IncidentRegister />, { wrapper })
    expect(screen.getByText('Loading incidents…')).toBeInTheDocument()
  })

  it('shows healthy empty state when there are no incidents', async () => {
    mockGet.mockResolvedValue({ data: { open_count: 0, p1_open: 0, incidents: [] } })
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('All systems healthy')).toBeInTheDocument())
  })

  it('renders summary counts and incident rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('API latency spike')).toBeInTheDocument())
    expect(screen.getByText('Consumer lag growing')).toBeInTheDocument()
    expect(screen.getByText('5xx rate above threshold')).toBeInTheDocument()
  })

  it('triggers a manual check run', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('API latency spike')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /run check now/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/pa/incidents/run-check', {}))
  })

  it('acknowledges an OPEN incident', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('API latency spike')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /acknowledge/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/pa/incidents/inc-1/acknowledge', {}))
  })

  it('resolves an incident with a resolution note', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('Consumer lag growing')).toBeInTheDocument())
    const resolveButtons = screen.getAllByRole('button', { name: /resolve/i })
    // inc-2 is ACKNOWLEDGED (only Resolve button, no Acknowledge) — it's the last Resolve button rendered.
    await user.click(resolveButtons[resolveButtons.length - 1])
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/pa/incidents/inc-2/resolve', { note: 'Manually resolved by PA' }))
  })

  it('handles run-check failure without crashing', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockRejectedValue(new Error('boom'))
    render(<IncidentRegister />, { wrapper })
    await waitFor(() => expect(screen.getByText('API latency spike')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /run check now/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    expect(screen.getByText('API latency spike')).toBeInTheDocument()
  })
})
