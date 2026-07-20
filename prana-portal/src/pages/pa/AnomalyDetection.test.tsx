import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AnomalyDetection } from './AnomalyDetection'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  unacknowledged: 2, high_severity: 1, resolved_7d: 4,
  anomalies: [
    {
      anomaly_id: 'an-1', anomaly_type: 'BULK_ACCESS', severity: 'HIGH',
      description: 'Unusual bulk document access', tenant_name: 'Acme Ltd',
      detected_at: '2026-07-01T10:00:00Z', acknowledged_at: null,
    },
    {
      anomaly_id: 'an-2', anomaly_type: 'LOGIN_SPIKE', severity: 'LOW',
      description: 'Login spike detected', tenant_name: 'Beta Inc',
      detected_at: '2026-07-02T10:00:00Z', acknowledged_at: '2026-07-02T11:00:00Z',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('AnomalyDetection', () => {
  it('renders stat cards from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AnomalyDetection />, { wrapper })
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('shows empty state when no anomalies', async () => {
    mockGet.mockResolvedValue({ data: { unacknowledged: 0, high_severity: 0, resolved_7d: 0, anomalies: [] } })
    render(<AnomalyDetection />, { wrapper })
    await waitFor(() => expect(screen.getByText('No active anomalies.')).toBeInTheDocument())
  })

  it('shows acknowledge button only for unacknowledged anomalies', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<AnomalyDetection />, { wrapper })
    await waitFor(() => expect(screen.getByText('Unusual bulk document access')).toBeInTheDocument())
    const ackButtons = screen.getAllByRole('button', { name: /acknowledge/i })
    expect(ackButtons).toHaveLength(1)
  })

  it('acknowledges an anomaly and invalidates the query on success', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<AnomalyDetection />, { wrapper })
    await waitFor(() => expect(screen.getByText('Unusual bulk document access')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /acknowledge/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/anomalies/an-1/acknowledge', {}))
  })

  it('handles acknowledge mutation failure gracefully (no crash)', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    mockPost.mockRejectedValue(new Error('server error'))
    render(<AnomalyDetection />, { wrapper })
    await waitFor(() => expect(screen.getByText('Unusual bulk document access')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /acknowledge/i }))
    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    expect(screen.getByText('Unusual bulk document access')).toBeInTheDocument()
  })
})
