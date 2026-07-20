/**
 * OnboardingQueue tests — TDD RED -> GREEN -> REFACTOR
 *
 *  1. Shows loading state while fetching
 *  2. Categorizes an unverified tenant into "Awaiting Domain Verification"
 *  3. Categorizes a verified, non-auto-approve tenant into "Pending PA Review"
 *  4. Categorizes an active AUTO_APPROVE tenant created today into "Auto-Approved Today"
 *  5. Shows a "Retry" action for VERIFICATION_FAILED tenants
 *  6. Shows empty state when no applications in any bucket
 *  7. Approve/reject/region-override actions on a Pending PA Review tenant
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { OnboardingQueue } from './OnboardingQueue'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const TODAY = new Date().toISOString()

function mockRoutes(overrides: Partial<Record<string, any>> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('status=PENDING')) return Promise.resolve({ data: overrides.pending ?? { tenants: [] } })
    if (url.includes('status=ACTIVE')) return Promise.resolve({ data: overrides.active ?? { tenants: [] } })
    if (url.includes('status=VERIFICATION_FAILED')) return Promise.resolve({ data: overrides.failed ?? { tenants: [] } })
    return Promise.resolve({ data: {} })
  })
}

const PENDING_REVIEW_TENANT = {
  tenant_id: 't-1', tenant_name: 'Acme Ltd', industry: 'IT & Software',
  domain: 'acme.in', cin: 'U72900MH2010PTC123456', employee_headcount_band: '201-500',
  approval_tier: 'PA_REVIEW', domain_verified_at: TODAY,
  verification_remaining_hours: null, home_region: null, created_at: TODAY,
}

beforeEach(() => vi.clearAllMocks())

describe('OnboardingQueue', () => {
  it('shows loading state while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<OnboardingQueue />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('categorizes an unverified tenant into Awaiting Domain Verification', async () => {
    mockRoutes({
      pending: { tenants: [{
        tenant_id: 't-1', tenant_name: 'SwiftHR Technologies', domain: 'swifthr.co.in',
        industry: 'IT & Software', employee_headcount_band: '1-50',
        approval_tier: 'AUTO_APPROVE', domain_verified_at: null,
        verification_remaining_hours: 40, created_at: TODAY,
      }] },
    })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('SwiftHR Technologies')).toBeInTheDocument())
    expect(screen.getByText(/awaiting domain verification/i)).toBeInTheDocument()
    expect(screen.getByText(/40h remaining/i)).toBeInTheDocument()
  })

  it('categorizes a verified BFSI tenant into Pending PA Review', async () => {
    mockRoutes({
      pending: { tenants: [{
        tenant_id: 't-2', tenant_name: 'FinServ Capital Ltd', domain: 'finservcapital.com',
        industry: 'Banking & Financial Services (BFSI)', employee_headcount_band: '201-500',
        approval_tier: 'PA_REVIEW', domain_verified_at: TODAY,
        verification_remaining_hours: null, created_at: TODAY,
      }] },
    })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('FinServ Capital Ltd')).toBeInTheDocument())
    expect(screen.getAllByText(/pending pa review/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/bfsi \/ large/i).length).toBeGreaterThan(0)
  })

  it('categorizes an auto-approved active tenant created today into Auto-Approved Today', async () => {
    mockRoutes({
      active: { tenants: [{
        tenant_id: 't-3', tenant_name: 'QuickPay Solutions', domain: 'quickpay.in',
        approval_tier: 'AUTO_APPROVE', home_region: 'ap-south-1', created_at: TODAY,
      }] },
    })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('QuickPay Solutions')).toBeInTheDocument())
    expect(screen.getAllByText(/auto-approved today/i).length).toBeGreaterThan(0)
  })

  it('shows a Retry action for VERIFICATION_FAILED tenants', async () => {
    mockRoutes({
      failed: { tenants: [{
        tenant_id: 't-4', tenant_name: 'Stuck Corp', domain: 'stuck.com',
        approval_tier: 'AUTO_APPROVE', created_at: TODAY,
      }] },
    })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Stuck Corp')).toBeInTheDocument())
    expect(screen.getByText(/verification failed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows empty state when no applications in any bucket', async () => {
    mockRoutes()
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText(/no pending applications/i)).toBeInTheDocument())
  })

  it('renders a Pending PA Review tenant application', async () => {
    mockRoutes({ pending: { tenants: [PENDING_REVIEW_TENANT] } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('acme.in')).toBeInTheDocument()
  })

  it('approves a tenant without region override', async () => {
    const user = userEvent.setup()
    mockRoutes({ pending: { tenants: [PENDING_REVIEW_TENANT] } })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    await user.click(screen.getByRole('button', { name: /confirm approval/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/tenants/t-1/activate', {
      home_region_override: undefined, override_reason: undefined,
    }))
  })

  it('requires an override reason before approving with a region override', async () => {
    const user = userEvent.setup()
    mockRoutes({ pending: { tenants: [PENDING_REVIEW_TENANT] } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    const regionSelect = screen.getByDisplayValue('Auto (recommended)')
    await user.selectOptions(regionSelect, 'ap-south-2')
    const confirmBtn = screen.getByRole('button', { name: /confirm approval/i })
    expect(confirmBtn).toBeDisabled()
    await user.type(screen.getByPlaceholderText('Reason for override (required)'), 'Employee base is in Hyderabad')
    expect(confirmBtn).not.toBeDisabled()
  })

  it('rejects a tenant application', async () => {
    const user = userEvent.setup()
    mockRoutes({ pending: { tenants: [PENDING_REVIEW_TENANT] } })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /reject/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/tenants/t-1/reject'))
  })
})
