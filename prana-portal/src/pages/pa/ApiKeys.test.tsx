import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ApiKeys } from './ApiKeys'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  tenants: [{ tenant_id: 't-1', tenant_name: 'Acme Ltd' }],
  keys: [
    { api_key_id: 'k-1', label: 'SAP integration', tenant_name: 'Acme Ltd', key_id_prefix: 'abcd1234', rate_limit_per_minute: 60, last_used_at: '2026-07-01T10:00:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('ApiKeys', () => {
  it('shows empty state when no keys exist', async () => {
    mockGet.mockResolvedValue({ data: { tenants: [], keys: [] } })
    render(<ApiKeys />, { wrapper })
    await waitFor(() => expect(screen.getByText('No active API keys.')).toBeInTheDocument())
  })

  it('renders active key rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ApiKeys />, { wrapper })
    await waitFor(() => expect(screen.getByText('SAP integration')).toBeInTheDocument())
    expect(screen.getByText('60/min')).toBeInTheDocument()
  })

  it('opens the issue-key form and creates a key', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { api_key: 'sk_live_abc123' } })
    render(<ApiKeys />, { wrapper })
    await waitFor(() => expect(screen.getByText('SAP integration')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /issue key/i }))
    await user.selectOptions(screen.getByText('Select tenant…').closest('select')!, 't-1')
    await user.type(screen.getByPlaceholderText('e.g. SAP HCM integration'), 'New Connector')

    const createButtons = screen.getAllByRole('button', { name: /issue key/i })
    await user.click(createButtons[createButtons.length - 1])

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/api-keys', {
      tenant_id: 't-1', label: 'New Connector', rate_limit_per_minute: 60,
    }))
    await waitFor(() => expect(screen.getByText(/Key created/)).toBeInTheDocument())
    expect(screen.getByText('sk_live_abc123')).toBeInTheDocument()

    // Regression guard: the created-key panel must stay visible until the PA
    // explicitly dismisses it via "Done" — it must not auto-close on mutation success.
    await user.click(screen.getByRole('button', { name: /^done$/i }))
    expect(screen.queryByText('sk_live_abc123')).not.toBeInTheDocument()
  })

  it('revokes an existing key', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<ApiKeys />, { wrapper })
    await waitFor(() => expect(screen.getByText('SAP integration')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /revoke/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/api-keys/k-1/revoke', {}))
  })

  it('disables create button until tenant and label are filled', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<ApiKeys />, { wrapper })
    await waitFor(() => expect(screen.getByText('SAP integration')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /issue key/i }))
    const createButtons = screen.getAllByRole('button', { name: /issue key/i })
    expect(createButtons[createButtons.length - 1]).toBeDisabled()
  })
})
