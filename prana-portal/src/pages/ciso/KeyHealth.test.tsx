/**
 * KeyHealth tests
 *
 *  1. Renders KEK status card with key id, state, region
 *  2. Renders TOTP secret encryption card
 *  3. Renders recent KMS events with outcome icon
 *  4. Shows "no events" empty state when events list is empty
 *  5. Shows placeholders ('—') when data is undefined (loading)
 *  6. StatusPill shows nothing when status is undefined
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { KeyHealth } from './KeyHealth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  kek_status: 'HEALTHY',
  kek_key_id: 'arn:aws:kms:ap-south-1:111:key/abc-123',
  kek_state: 'Enabled',
  kek_created_at: '2025-01-10T00:00:00Z',
  kek_last_used_at: '2026-07-01T08:00:00Z',
  dek_count: 4820,
  totp_enc_status: 'ENABLED',
  totp_secret_count: 312,
  events: [
    { event_type: 'KMS_DECRYPT', outcome: 'SUCCESS', occurred_at: '2026-07-01T08:00:00Z' },
    { event_type: 'KMS_ROTATE', outcome: 'FAILED', occurred_at: '2026-06-20T08:00:00Z' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('KeyHealth', () => {
  it('renders tenant KEK card with key id, state, and region', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<KeyHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText(MOCK.kek_key_id)).toBeInTheDocument())
    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.getAllByText('ap-south-1').length).toBeGreaterThan(0)
    expect(screen.getByText('HEALTHY')).toBeInTheDocument()
  })

  it('renders TOTP secret encryption card with algorithm and count', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<KeyHealth />, { wrapper })
    // "AES-256-GCM" is a static label (KeyHealth.tsx:46), not derived from `data`
    // — it renders on the very first paint, before the query resolves. Wait on
    // the actual query-derived value instead, or this assertion can pass while
    // the count field is still showing its pre-load "—" fallback.
    expect(await screen.findByText('312')).toBeInTheDocument()
    expect(screen.getByText('AES-256-GCM')).toBeInTheDocument()
    expect(screen.getByText('ENABLED')).toBeInTheDocument()
  })

  it('renders recent KMS events list', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<KeyHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('KMS_DECRYPT')).toBeInTheDocument())
    expect(screen.getByText('KMS_ROTATE')).toBeInTheDocument()
  })

  it('shows empty state when there are no KMS events', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, events: [] } })
    render(<KeyHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('No KMS events recorded.')).toBeInTheDocument())
  })

  it('renders placeholder dashes before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<KeyHealth />, { wrapper })
    expect(screen.getByText('Key Health')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})
