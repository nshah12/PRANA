import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PlatformCredentials } from './PlatformCredentials'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const COMM_CREDENTIALS_MOCK = {
  vendors: {
    ses: { configured: true, source: 'env' },
    msg91: { configured: false, source: 'none' },
  },
  editable_fields: {
    msg91: ['msg91_auth_key'],
  },
}

const PLATFORM_CREDENTIALS_MOCK = {
  vendors: {
    qdrant: { configured: false, source: 'none' },
  },
  editable_fields: {
    qdrant: ['qdrant_url', 'qdrant_api_key'],
  },
}

function mockBothSources() {
  mockGet.mockImplementation((url: string) =>
    url.includes('/admin/platform-credentials')
      ? Promise.resolve({ data: PLATFORM_CREDENTIALS_MOCK })
      : Promise.resolve({ data: COMM_CREDENTIALS_MOCK }))
}

beforeEach(() => vi.clearAllMocks())

describe('PlatformCredentials (PA)', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<PlatformCredentials />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state on load failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<PlatformCredentials />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load platform credentials.')).toBeInTheDocument())
  })

  it('merges communication vendors and platform credentials into one list', async () => {
    mockBothSources()
    render(<PlatformCredentials />, { wrapper })
    await waitFor(() => expect(screen.getByText('ses')).toBeInTheDocument())
    expect(screen.getByText('msg91')).toBeInTheDocument()
    expect(screen.getByText('qdrant')).toBeInTheDocument()
  })

  it('shows editable fields for qdrant', async () => {
    mockBothSources()
    render(<PlatformCredentials />, { wrapper })
    await waitFor(() => expect(screen.getByText('qdrant_url')).toBeInTheDocument())
    expect(screen.getByText('qdrant_api_key')).toBeInTheDocument()
  })

  it('saving a qdrant field calls the /admin/platform-credentials endpoint, not the comm one', async () => {
    const user = userEvent.setup()
    mockBothSources()
    mockPatch.mockResolvedValue({ data: { message: 'PLATFORM_CREDENTIAL_ROTATED', vendor: 'qdrant', field_name: 'qdrant_api_key' } })
    render(<PlatformCredentials />, { wrapper })
    await waitFor(() => expect(screen.getByText('qdrant_api_key')).toBeInTheDocument())

    const row = screen.getByText('qdrant_api_key').closest('div')!
    await user.click(within(row).getByRole('button', { name: /^set$/i }))
    const input = screen.getByPlaceholderText('Enter new value')
    expect(input).toHaveAttribute('type', 'password')
    await user.type(input, 'real-qdrant-key-123')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/admin/platform-credentials/qdrant',
      { field_name: 'qdrant_api_key', value: 'real-qdrant-key-123' },
    ))
    expect(screen.queryByText('real-qdrant-key-123')).not.toBeInTheDocument()
  })

  it('saving a comm-vendor field still calls the /admin/communications/vendor-credentials endpoint', async () => {
    const user = userEvent.setup()
    mockBothSources()
    mockPatch.mockResolvedValue({ data: { message: 'COMM_VENDOR_CREDENTIAL_ROTATED', vendor: 'msg91', field_name: 'msg91_auth_key' } })
    render(<PlatformCredentials />, { wrapper })
    await waitFor(() => expect(screen.getByText('msg91_auth_key')).toBeInTheDocument())

    const row = screen.getByText('msg91_auth_key').closest('div')!
    await user.click(within(row.parentElement!).getByRole('button', { name: /^set$/i }))
    await user.type(screen.getByPlaceholderText('Enter new value'), 'real-secret-value')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/admin/communications/vendor-credentials/msg91',
      { field_name: 'msg91_auth_key', value: 'real-secret-value' },
    ))
  })
})
