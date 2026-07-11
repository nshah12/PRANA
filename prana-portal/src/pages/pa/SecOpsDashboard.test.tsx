import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SecOpsDashboard } from './SecOpsDashboard'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  active_threats: 2, locked_accounts: 5, auth_events_1h: 120, foreign_ips_24h: 3,
  tenants: [
    { tenant_id: 't-1', tenant_name: 'Acme Ltd', posture: 'GREEN', locked_count: 1, anomaly_count: 0, last_threat_at: null },
    { tenant_id: 't-2', tenant_name: 'Beta Inc', posture: 'RED', locked_count: 4, anomaly_count: 2, last_threat_at: '2026-07-01T10:00:00Z' },
  ],
  alerts: [
    { severity: 'HIGH', description: 'Bulk access anomaly', tenant_name: 'Beta Inc', occurred_at: '2026-07-02T10:00:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('SecOpsDashboard', () => {
  it('shows loading skeleton before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<SecOpsDashboard />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows error state with retry on failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load SecOps dashboard.')).toBeInTheDocument())
    const retryBtn = screen.getByRole('button', { name: /retry/i })
    mockGet.mockResolvedValue({ data: MOCK })
    await retryBtn.click()
  })

  it('renders stat cards from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('120')).toBeInTheDocument())
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders tenant posture table rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getAllByText('Beta Inc').length).toBeGreaterThan(0)
    expect(screen.getByText('GREEN')).toBeInTheDocument()
    expect(screen.getByText('RED')).toBeInTheDocument()
  })

  it('shows empty state for tenant table when no tenants', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, tenants: [] } })
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('No tenant data.')).toBeInTheDocument())
  })

  it('shows empty state for alert feed when no alerts', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, alerts: [] } })
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('No active alerts.')).toBeInTheDocument())
  })

  it('renders live alert feed entries', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<SecOpsDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Bulk access anomaly')).toBeInTheDocument())
  })
})
