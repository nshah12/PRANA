import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CommunicationSettings } from './CommunicationSettings'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const POLICY_MOCK = {
  items: [
    { template_id: 'OA_WELCOME', channels: ['email'], platform_channels: ['email'], is_tenant_override: false },
    { template_id: 'VAULT_WELCOME', channels: ['email'], platform_channels: ['sms', 'email'], is_tenant_override: true },
  ],
}

const CHAINS_MOCK = {
  chains: {
    sms: { chain: ['aws'], available_vendors: ['aws', 'exotel', 'msg91'] },
  },
}

beforeEach(() => vi.clearAllMocks())

describe('CommunicationSettings (OA-Admin)', () => {
  it('shows loading skeleton while fetching channel policy', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CommunicationSettings />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('renders channel policy rows with override badges', async () => {
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())
    expect(screen.getByText('Platform default')).toBeInTheDocument()
    expect(screen.getByText('Tenant override')).toBeInTheDocument()
  })

  it('edits a channel policy row and writes a tenant override', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    mockPatch.mockResolvedValue({ data: { message: 'COMM_CHANNEL_POLICY_UPDATED', channel_policy: {} } })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getAllByRole('button', { name: /^edit$/i })[0])
    await user.click(screen.getByRole('checkbox', { name: /sms/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/v1/org/communications/channel-policy/OA_WELCOME',
      { channels: expect.arrayContaining(['email', 'sms']) },
    ))
  })

  it('resets a tenant override back to the platform default', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    mockPatch.mockResolvedValue({ data: { message: 'COMM_CHANNEL_POLICY_UPDATED', channel_policy: {} } })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('VAULT_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByTitle('Reset to platform default'))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/v1/org/communications/channel-policy/VAULT_WELCOME',
      { channels: ['sms', 'email'] },
    ))
  })

  it('renders vendor chain tab scoped to enabled vendors', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-chains') ? Promise.resolve({ data: CHAINS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor chains/i }))
    await waitFor(() => expect(screen.getByText('1. aws')).toBeInTheDocument())
  })

  it('has no vendor credentials tab at all', async () => {
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /vendor credentials/i })).not.toBeInTheDocument()
  })
})
