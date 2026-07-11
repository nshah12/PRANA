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
  active_tenants: 42, total_employees: 15000, storage_used_label: '3.2 TB', open_exceptions: 7,
  pipeline_counts: { QUEUED: 10, ENCRYPTING: 2, SCANNING: 1, EXTRACTING: 3, RESOLVING: 5 },
  recent_tenant_activity: [
    { tenant_name: 'Acme Ltd', type: 'PROVISIONED' },
    { tenant_name: 'Beta Inc', type: 'SUSPENDED' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('MetaDashboard', () => {
  it('shows loading skeleton before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<MetaDashboard />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('down'))
    render(<MetaDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load platform dashboard.')).toBeInTheDocument())
  })

  it('renders stat cards from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('42')).toBeInTheDocument())
    expect(screen.getByText('15000')).toBeInTheDocument()
    expect(screen.getByText('3.2 TB')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('renders pipeline health stage bars', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('QUEUED')).toBeInTheDocument())
    expect(screen.getByText('RESOLVING')).toBeInTheDocument()
  })

  it('renders recent tenant activity feed', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('PROVISIONED')).toBeInTheDocument()
  })

  it('shows empty state fallback when no recent activity', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, recent_tenant_activity: undefined } })
    render(<MetaDashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('No recent activity.')).toBeInTheDocument())
  })
})
