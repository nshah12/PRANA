import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { RateLimits } from './RateLimits'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  total_keys: 12, throttled_1h: 2, avg_rpm: 45, platform_default_rpm: 60,
  tenant_defaults: [
    { tenant_id: 't-1', tenant_name: 'Acme Ltd', default_rpm: 100, source: 'tenant_config' },
    { tenant_id: 't-2', tenant_name: 'Beta Inc', default_rpm: 60, source: 'platform_config' },
  ],
  keys: [
    { api_key_id: 'k-1', tenant_name: 'Acme Ltd', label: 'SAP integration', rate_limit_rpm: 100, status: 'ACTIVE' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('RateLimits', () => {
  it('shows loading rows while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<RateLimits />, { wrapper })
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0)
  })

  it('renders stat cards from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<RateLimits />, { wrapper })
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument())
    expect(screen.getByText('45')).toBeInTheDocument()
  })

  it('renders tenant default rate limit rows with source badges', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<RateLimits />, { wrapper })
    // "Acme Ltd" appears in both the tenant-defaults table AND the per-key
    // overrides table (MOCK.keys[0].tenant_name is also 'Acme Ltd') — scope
    // to the "Per-tenant default rate limits" table via its heading's container.
    // The heading itself is static (renders before the query resolves), so use
    // findBy (retrying) rather than getBy for the row content within it.
    const heading = screen.getByText('Per-tenant default rate limits')
    const table = within(heading.closest('.bg-white') as HTMLElement)
    expect(await table.findByText('Acme Ltd')).toBeInTheDocument()
    expect(table.getByText('custom')).toBeInTheDocument()
    expect(table.getByText('platform default')).toBeInTheDocument()
  })

  it('renders per-key override rows', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<RateLimits />, { wrapper })
    await waitFor(() => expect(screen.getByText('SAP integration')).toBeInTheDocument())
  })

  it('shows empty state when there are no key overrides', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, keys: [] } })
    render(<RateLimits />, { wrapper })
    await waitFor(() => expect(screen.getByText('No HRMS API keys issued yet. Use "API Keys" to issue one.')).toBeInTheDocument())
  })
})
