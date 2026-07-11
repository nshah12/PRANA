import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { HRMSCatalogue } from './HRMSCatalogue'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  items: [
    {
      connector_definition_id: 'conn-1', connector_key: 'darwinbox', display_name: 'Darwinbox',
      auth_method: 'OAUTH2', supported_modes: ['PULL', 'WEBHOOK'], docs_url: 'https://docs.example.com/darwinbox',
      is_active: true,
    },
    {
      connector_definition_id: 'conn-2', connector_key: 'keka', display_name: 'Keka',
      auth_method: 'API_KEY', supported_modes: ['PULL'], docs_url: undefined,
      is_active: false,
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('HRMSCatalogue', () => {
  it('shows loading state while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<HRMSCatalogue />, { wrapper })
    expect(screen.getByText('Loading connectors…')).toBeInTheDocument()
  })

  it('shows error state on failure', async () => {
    mockGet.mockRejectedValue(new Error('down'))
    render(<HRMSCatalogue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load connector catalogue. Retry later.')).toBeInTheDocument())
  })

  it('shows empty state when there are no connector definitions', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<HRMSCatalogue />, { wrapper })
    await waitFor(() => expect(screen.getByText('No connector definitions yet.')).toBeInTheDocument())
  })

  it('renders connector cards with auth method and modes', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<HRMSCatalogue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Darwinbox')).toBeInTheDocument())
    expect(screen.getByText('Keka')).toBeInTheDocument()
    expect(screen.getByText('OAUTH2')).toBeInTheDocument()
    expect(screen.getByText('API_KEY')).toBeInTheDocument()
  })

  it('deactivates an active connector', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<HRMSCatalogue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Darwinbox')).toBeInTheDocument())
    const darwinboxCard = screen.getByText('Darwinbox').closest('div.bg-white')!
    const toggleBtn = darwinboxCard.querySelector('button')!
    await user.click(toggleBtn)
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/v1/admin/hrms/definitions/conn-1/deactivate'))
  })

  it('activates an inactive connector', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<HRMSCatalogue />, { wrapper })
    await waitFor(() => expect(screen.getByText('Keka')).toBeInTheDocument())
    const kekaCard = screen.getByText('Keka').closest('div.bg-white')!
    const toggleBtn = kekaCard.querySelector('button')!
    await user.click(toggleBtn)
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/v1/admin/hrms/definitions/conn-2/activate'))
  })
})
