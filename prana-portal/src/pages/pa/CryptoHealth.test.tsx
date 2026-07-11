import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CryptoHealth } from './CryptoHealth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  hmac_key_status: 'ENABLED', fpe_key_status: 'ENABLED', totp_key_status: 'ENABLED',
  tenant_keys: [
    { tenant_id: 't-1', tenant_name: 'Acme Ltd', kms_key_id: 'kms-key-1', key_state: 'ACTIVE', dek_count: 12, last_rotated_at: '2026-06-01T10:00:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('CryptoHealth', () => {
  it('renders platform key summary cards with status', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CryptoHealth />, { wrapper })
    await waitFor(() => expect(screen.getAllByText('ENABLED')).toHaveLength(3))
  })

  it('shows empty state when there are no tenant keys', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, tenant_keys: [] } })
    render(<CryptoHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('No tenant keys found.')).toBeInTheDocument())
  })

  it('renders tenant KEK rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CryptoHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('Acme Ltd')).toBeInTheDocument())
    expect(screen.getByText('kms-key-1')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('shows UNKNOWN status fallback before data resolves (default query state)', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CryptoHealth />, { wrapper })
    expect(screen.getAllByText('UNKNOWN').length).toBeGreaterThan(0)
  })

  it('renders the fixed algorithm inventory list regardless of query data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CryptoHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('PAN dedup token')).toBeInTheDocument())
    expect(screen.getByText('Argon2id')).toBeInTheDocument()
  })
})
