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

const MOCK = {
  tenants: [
    {
      tenant_id: 't-1', tenant_name: 'Acme Ltd', industry: 'IT & Software', tier: 'STANDARD',
      domain: 'acme.in', cin: 'U72900MH2010PTC123456', employee_size_band: '201-500',
      home_region: null, created_at: '2026-07-01T10:00:00Z',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('OnboardingQueue', () => {
  it('shows loading text while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<OnboardingQueue />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows empty state when there are no pending tenants', async () => {
    mockGet.mockResolvedValue({ data: { tenants: [] } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('No pending applications')).toBeInTheDocument())
  })

  it('renders pending tenant applications', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('acme.in')).toBeInTheDocument()
  })

  it('approves a tenant without region override', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
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
    mockGet.mockResolvedValue({ data: MOCK })
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
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<OnboardingQueue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /reject/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/tenants/t-1/reject'))
  })
})
