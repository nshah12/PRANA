/**
 * MetaDashboard tests — TDD RED -> GREEN -> REFACTOR
 *
 *  1. Shows loading skeleton while fetching
 *  2. Shows error state with retry button on failure
 *  3. Renders pending-approval sub-label on the active-tenants tile
 *  4. Renders SLA-breach sub-label on the open-exceptions tile
 *  5. Renders the Security Alerts panel with real counts
 *  6. Renders the Top Tenants by Activity table
 *  7. Shows an empty state when no tenant activity yet today
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { MetaDashboard } from './MetaDashboard'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  active_tenants: 47,
  total_employees: 1200000,
  storage_used_label: '18.4 GB',
  open_exceptions: 14,
  pending_approval_count: 3,
  sla_breach_count: 2,
  security_alerts: {
    failed_logins_24h: 34,
    quarantined_files: 2,
    csam_events: 0,
    rate_limit_hits_24h: 0,
  },
  top_tenants: [
    { tenant_id: 't-1', tenant_name: 'NPCI', status: 'ACTIVE', docs_today: 1843, open_exceptions: 0 },
  ],
  llm_usage_today: {
    extraction_calls: 5104,
    tokens_consumed: 12400000,
    avg_confidence: 0.91,
    estimated_cost_inr: 10540.0,
  },
  pipeline_counts: {},
  recent_tenant_activity: [],
}

beforeEach(() => vi.clearAllMocks())

describe('MetaDashboard', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<MetaDashboard />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders pending-approval sub-label on the active-tenants tile', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/\+3 pending approval/i)).toBeInTheDocument()
    )
  })

  it('renders SLA-breach sub-label on the open-exceptions tile', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/2 tenants breaching SLA/i)).toBeInTheDocument()
    )
  })

  it('renders the Security Alerts panel with real counts', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/security alerts/i)).toBeInTheDocument()
    )
    expect(screen.getByText('34')).toBeInTheDocument()
    expect(screen.getByText(/failed logins/i)).toBeInTheDocument()
  })

  it('renders the LLM Usage panel with real counts', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/llm usage/i)).toBeInTheDocument()
    )
    expect(screen.getByText('5,104')).toBeInTheDocument()
    expect(screen.getByText('₹10,540')).toBeInTheDocument()
  })

  it('renders the Top Tenants by Activity table', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/top tenants by activity/i)).toBeInTheDocument()
    )
    expect(screen.getByText('NPCI')).toBeInTheDocument()
    expect(screen.getByText('1843')).toBeInTheDocument()
  })

  it('shows an empty state when no tenant activity yet today', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, top_tenants: [] } })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/no activity yet today/i)).toBeInTheDocument()
    )
  })
})
