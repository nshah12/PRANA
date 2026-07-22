/**
 * TenantDetail tests — TDD RED -> GREEN -> REFACTOR
 *
 *  1. Shows loading skeleton while fetching
 *  2. Shows error state with retry button on failure
 *  3. Renders tenant name, domain, and status badge
 *  4. Shows a Suspend button for an ACTIVE tenant, not Reinstate
 *  5. Shows a Reinstate button for a SUSPENDED tenant, not Suspend
 *  6. Renders the static Tenant Lifecycle States reference table
 *  7. Suspend button opens a reason prompt and calls the suspend endpoint
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { TenantDetail } from './TenantDetail'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/tenants/tenant-xyz']}>
        <Routes>
          <Route path="/admin/tenants/:id" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const ACTIVE_TENANT = {
  tenant_id: 'tenant-xyz', tenant_name: 'NPCI', domain: 'npci.org.in',
  status: 'ACTIVE', industry: 'Banking & Financial Services (BFSI)',
  employee_headcount_band: '2001-10000', sla_tier: 'ENTERPRISE',
  home_region: 'ap-south-1', created_at: '2024-01-01T00:00:00Z',
  domain_verified_at: '2024-01-01T00:00:00Z',
}

const SUSPENDED_TENANT = { ...ACTIVE_TENANT, status: 'SUSPENDED' }

beforeEach(() => {
  vi.clearAllMocks()
  window.confirm = vi.fn(() => true)
  window.prompt = vi.fn(() => 'Non-payment')
})

describe('TenantDetail', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<TenantDetail />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument())
  })

  it('renders tenant name, domain, and status badge', async () => {
    mockGet.mockResolvedValue({ data: { tenant: ACTIVE_TENANT } })
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByText('NPCI')).toBeInTheDocument())
    expect(screen.getByText('npci.org.in')).toBeInTheDocument()
    expect(screen.getAllByText('ACTIVE').length).toBeGreaterThan(0)
  })

  it('shows Suspend (not Reinstate) for an ACTIVE tenant', async () => {
    mockGet.mockResolvedValue({ data: { tenant: ACTIVE_TENANT } })
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByRole('button', { name: /suspend/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /reinstate/i })).not.toBeInTheDocument()
  })

  it('shows Reinstate (not Suspend) for a SUSPENDED tenant', async () => {
    mockGet.mockResolvedValue({ data: { tenant: SUSPENDED_TENANT } })
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByRole('button', { name: /reinstate/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /^suspend$/i })).not.toBeInTheDocument()
  })

  it('renders the Tenant Lifecycle States reference table', async () => {
    mockGet.mockResolvedValue({ data: { tenant: ACTIVE_TENANT } })
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByText(/tenant lifecycle states/i)).toBeInTheDocument())
    expect(screen.getByText(/alumni access/i)).toBeInTheDocument()
  })

  it('Suspend button prompts for a reason and calls the suspend endpoint', async () => {
    mockGet.mockResolvedValue({ data: { tenant: ACTIVE_TENANT } })
    mockPost.mockResolvedValue({ data: { message: 'Tenant suspended' } })
    const user = userEvent.setup()
    render(<TenantDetail />, { wrapper })
    await waitFor(() => expect(screen.getByRole('button', { name: /suspend/i })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /suspend/i }))

    expect(window.prompt).toHaveBeenCalled()
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/admin/tenants/tenant-xyz/suspend', { reason: 'Non-payment' })
    )
  })
})
