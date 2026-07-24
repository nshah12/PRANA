import { render, screen, waitFor, within } from '@testing-library/react'
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
    { template_id: 'VAULT_WELCOME', channels: ['sms', 'email'], platform_channels: ['sms', 'email'], is_tenant_override: false },
  ],
}

const CHAINS_MOCK = {
  chains: {
    email: { chain: ['ses'], available_vendors: ['ses', 'smtp'] },
    sms: { chain: ['aws', 'exotel', 'msg91'], available_vendors: ['aws', 'exotel', 'msg91'] },
  },
}

const CREDENTIALS_MOCK = {
  vendors: {
    ses: { configured: true, source: 'env' },
    smtp: { configured: false, source: 'none' },
    msg91: { configured: false, source: 'none' },
  },
  editable_fields: {
    smtp: ['smtp_host', 'smtp_user', 'smtp_password'],
    msg91: ['msg91_auth_key'],
  },
}

beforeEach(() => vi.clearAllMocks())

describe('CommunicationSettings (PA)', () => {
  it('shows loading skeleton while fetching channel policy', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CommunicationSettings />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state with retry on load failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load channel policy.')).toBeInTheDocument())
  })

  it('renders channel policy rows on the default tab', async () => {
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())
    expect(screen.getByText('VAULT_WELCOME')).toBeInTheDocument()
  })

  it('edits a channel policy row and saves', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: POLICY_MOCK })
    mockPatch.mockResolvedValue({ data: { message: 'COMM_CHANNEL_POLICY_UPDATED', channel_policy: {} } })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getAllByRole('button', { name: /^edit$/i })[0])
    await user.click(screen.getByRole('checkbox', { name: /sms/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/admin/communications/channel-policy/OA_WELCOME',
      { channels: expect.arrayContaining(['email', 'sms']) },
    ))
  })

  it('renders vendor chains tab', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-chains') ? Promise.resolve({ data: CHAINS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor chains/i }))
    await waitFor(() => expect(screen.getByText('1. ses')).toBeInTheDocument())
  })

  it('renders vendor credentials tab without leaking secret values', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-credentials') ? Promise.resolve({ data: CREDENTIALS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor credentials/i }))
    await waitFor(() => expect(screen.getByText('ses')).toBeInTheDocument())
    expect(screen.getByText('Configured')).toBeInTheDocument()
    expect(screen.getAllByText('Not configured').length).toBeGreaterThan(0)
  })

  it('shows a Set button for each editable field, none for vendors with no editable fields', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-credentials') ? Promise.resolve({ data: CREDENTIALS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor credentials/i }))
    await waitFor(() => expect(screen.getByText('smtp_host')).toBeInTheDocument())
    expect(screen.getByText('smtp_user')).toBeInTheDocument()
    expect(screen.getByText('smtp_password')).toBeInTheDocument()
    expect(screen.getByText('msg91_auth_key')).toBeInTheDocument()
    // ses has no editable_fields entry — no field rows, no Set button under it
    expect(screen.getAllByRole('button', { name: /^set$/i }).length).toBe(4)
  })

  it('entering and saving a credential value never displays it, and calls the PATCH endpoint', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-credentials') ? Promise.resolve({ data: CREDENTIALS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    mockPatch.mockResolvedValue({ data: { message: 'COMM_VENDOR_CREDENTIAL_ROTATED', vendor: 'msg91', field_name: 'msg91_auth_key' } })
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor credentials/i }))
    await waitFor(() => expect(screen.getByText('msg91_auth_key')).toBeInTheDocument())

    const msg91Row = screen.getByText('msg91_auth_key').closest('div')!
    await user.click(within(msg91Row.parentElement!).getByRole('button', { name: /^set$/i }))

    const input = screen.getByPlaceholderText('Enter new value')
    expect(input).toHaveAttribute('type', 'password')
    await user.type(input, 'real-secret-value-123')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/admin/communications/vendor-credentials/msg91',
      { field_name: 'msg91_auth_key', value: 'real-secret-value-123' },
    ))
    // Secret value never appears anywhere in the rendered DOM after save
    expect(screen.queryByText('real-secret-value-123')).not.toBeInTheDocument()
  })

  it('save button is disabled until a value is entered', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-credentials') ? Promise.resolve({ data: CREDENTIALS_MOCK }) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor credentials/i }))
    await waitFor(() => expect(screen.getByText('msg91_auth_key')).toBeInTheDocument())

    const msg91Row = screen.getByText('msg91_auth_key').closest('div')!
    await user.click(within(msg91Row.parentElement!).getByRole('button', { name: /^set$/i }))
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
  })

  it('shows credential error state with retry on load failure', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      url.includes('vendor-credentials') ? Promise.reject(new Error('network down')) : Promise.resolve({ data: POLICY_MOCK }))
    render(<CommunicationSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText('OA_WELCOME')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /vendor credentials/i }))
    await waitFor(() => expect(screen.getByText('Failed to load vendor credentials.')).toBeInTheDocument())
  })
})
