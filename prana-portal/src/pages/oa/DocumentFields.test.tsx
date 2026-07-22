/**
 * DocumentFields tests
 *
 *  1. Loading state
 *  2. Error state with retry
 *  3. Empty state — no manifests configured
 *  4. Renders doc type list and the first doc type's fields, safe fields pre-checked
 *  5. OA-Admin: toggling a field and saving calls PUT with the full manifest + updated safe_fields
 *  6. OA-Admin: tenant-override badge shown when is_tenant_override is true
 *  7. OA-Operator: cannot see the save button (view-only)
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DocumentFields } from './DocumentFields'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), put: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPut = vi.mocked(api.put)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function setUser(role: 'oa_operator' | 'oa_admin') {
  useAuthStore.getState().setUser({
    userId: 'u-1', email: 'x@acme.example', displayName: 'X',
    role, tenantId: 't-1', tenantName: 'Acme Ltd',
  })
}

function makeManifest(overrides: Partial<any> = {}) {
  return {
    manifest_id: 'm-1',
    doc_type: 'SALARY_SLIP',
    required_fields: ['designation'],
    identity_fields: ['employee_id'],
    optional_fields: ['leave_balance_days'],
    classification_signals: [],
    signal_weights: [],
    confidence_threshold: 0.75,
    supported_formats: ['pdf'],
    safe_fields: ['designation'],
    is_active: true,
    is_tenant_override: false,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('DocumentFields', () => {
  it('shows a loading skeleton before data resolves', () => {
    setUser('oa_admin')
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = render(<DocumentFields />, { wrapper })
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an error state with a retry button on load failure', async () => {
    setUser('oa_admin')
    mockGet.mockRejectedValue(new Error('network'))
    render(<DocumentFields />, { wrapper })
    expect(await screen.findByText('Failed to load document field manifests.')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('shows an empty state when no manifests are configured', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } })
    render(<DocumentFields />, { wrapper })
    expect(await screen.findByText('No document field manifests configured for your organisation yet.')).toBeInTheDocument()
  })

  it('renders the doc type list and pre-checks safe fields for the first doc type', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [makeManifest()], total: 1 } })
    render(<DocumentFields />, { wrapper })

    expect(await screen.findByText('SALARY_SLIP')).toBeInTheDocument()
    expect(screen.getByText('designation')).toBeInTheDocument()
    expect(screen.getByText('employee_id')).toBeInTheDocument()
    expect(screen.getByText('leave_balance_days')).toBeInTheDocument()

    // designation is safe — its toggle should be checked (emerald fill). The
    // safe-fields Set syncs from `current` in a follow-up effect, one render
    // after the doc type list itself appears — wait for it like OrgSettings.test.tsx does.
    await waitFor(() => {
      const designationToggle = screen.getByText('designation').closest('label')!.querySelector('div')!
      expect(designationToggle.className).toMatch(/bg-emerald-600/)
    })
    // leave_balance_days is not in safe_fields — should be unchecked
    const leaveToggle = screen.getByText('leave_balance_days').closest('label')!.querySelector('div')!
    expect(leaveToggle.className).not.toMatch(/bg-emerald-600/)
  })

  it('OA-Admin: toggling a field and saving calls PUT with the full manifest and updated safe_fields', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [makeManifest()], total: 1 } })
    mockPut.mockResolvedValue({ data: {} })
    render(<DocumentFields />, { wrapper })
    await screen.findByText('leave_balance_days')

    const user = userEvent.setup()
    await user.click(screen.getByText('leave_balance_days'))
    await user.click(screen.getByRole('button', { name: /Save changes/ }))

    await waitFor(() => expect(mockPut).toHaveBeenCalledWith('/v1/manifests/SALARY_SLIP', expect.objectContaining({
      required_fields: ['designation'],
      identity_fields: ['employee_id'],
      optional_fields: ['leave_balance_days'],
      safe_fields: expect.arrayContaining(['designation', 'leave_balance_days']),
    })))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('shows the tenant-override badge when is_tenant_override is true', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [makeManifest({ is_tenant_override: true })], total: 1 } })
    render(<DocumentFields />, { wrapper })
    expect(await screen.findByText('Custom')).toBeInTheDocument()
  })

  it('OA-Operator: view-only — no save button, toggles are disabled', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { items: [makeManifest()], total: 1 } })
    render(<DocumentFields />, { wrapper })
    await screen.findByText('designation')

    expect(screen.queryByRole('button', { name: /Save changes/ })).not.toBeInTheDocument()
  })
})
