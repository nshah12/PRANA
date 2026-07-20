import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

import { TenantDirectory } from './TenantDirectory'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  tenants: [
    {
      tenant_id: 't-1', tenant_name: 'Acme Ltd', domain: 'acme.in', industry: 'IT & Software',
      employee_headcount_band: '201-500', primary_state: 'Maharashtra', sla_tier: 'ENTERPRISE',
      status: 'ACTIVE', cin: 'U72900MH2010PTC123456', created_at: '2026-01-01T10:00:00Z',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('TenantDirectory', () => {
  it('shows loading row while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<TenantDirectory />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows empty state when no tenants found', async () => {
    mockGet.mockResolvedValue({ data: { tenants: [] } })
    render(<TenantDirectory />, { wrapper })
    await waitFor(() => expect(screen.getByText('No tenants found')).toBeInTheDocument())
  })

  it('renders tenant rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<TenantDirectory />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('acme.in')).toBeInTheDocument()
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
  })

  it('navigates to tenant detail on row click', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<TenantDirectory />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByText('Acme Ltd'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/tenants/t-1')
  })

  it('navigates to new tenant wizard from header button', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<TenantDirectory />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /new tenant/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/tenants/new')
  })

  it('searches by query text', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<TenantDirectory />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    const search = screen.getByPlaceholderText(/search/i)
    await user.type(search, 'Acme')
    await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith('/admin/tenants', { params: { q: 'Acme' } }))
  })
})
