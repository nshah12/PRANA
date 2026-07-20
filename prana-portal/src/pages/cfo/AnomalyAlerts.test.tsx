/**
 * AnomalyAlerts tests
 *
 *  1. Renders title + subtitle (no employee identity shown — CFO sees financial pattern only)
 *  2. Empty state — no active anomalies
 *  3. Renders list of anomalies with severity badges
 *  4. Active count badge shown when anomalies present
 *  5. Acknowledge mutation — success invalidates query (refetch)
 *  6. Acknowledge mutation — error path (button re-enabled, no crash)
 *  7. Acknowledge button disabled while pending
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AnomalyAlerts } from './AnomalyAlerts'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK_ANOMALIES = [
  {
    anomaly_id: 'an-1',
    type: 'DUPLICATE_PAYMENT',
    severity: 'HIGH',
    financial_pattern: 'Two salary credits detected in same cycle',
    detected_at: '2026-06-20T10:00:00Z',
  },
  {
    anomaly_id: 'an-2',
    type: 'UNUSUAL_REIMBURSEMENT',
    severity: 'MEDIUM',
    financial_pattern: 'Reimbursement 3x higher than historical average',
    detected_at: '2026-06-21T11:30:00Z',
  },
]

beforeEach(() => vi.clearAllMocks())

describe('AnomalyAlerts', () => {
  it('renders title and privacy subtitle', async () => {
    mockGet.mockResolvedValue({ data: { anomalies: [] } })
    render(<AnomalyAlerts />, { wrapper })
    expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument()
    expect(screen.getByText(/No employee identity shown/i)).toBeInTheDocument()
  })

  it('shows empty state when there are no active anomalies', async () => {
    mockGet.mockResolvedValue({ data: { anomalies: [] } })
    render(<AnomalyAlerts />, { wrapper })
    expect(await screen.findByText('No active anomalies')).toBeInTheDocument()
  })

  it('renders anomaly list with severity badges', async () => {
    mockGet.mockResolvedValue({ data: { anomalies: MOCK_ANOMALIES } })
    render(<AnomalyAlerts />, { wrapper })
    expect(await screen.findByText('DUPLICATE PAYMENT')).toBeInTheDocument()
    expect(screen.getByText('UNUSUAL REIMBURSEMENT')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
  })

  it('shows active count badge when anomalies are present', async () => {
    mockGet.mockResolvedValue({ data: { anomalies: MOCK_ANOMALIES } })
    render(<AnomalyAlerts />, { wrapper })
    expect(await screen.findByText('2 active')).toBeInTheDocument()
  })

  it('does not show active count badge when list is empty', async () => {
    mockGet.mockResolvedValue({ data: { anomalies: [] } })
    render(<AnomalyAlerts />, { wrapper })
    await screen.findByText('No active anomalies')
    expect(screen.queryByText(/active$/)).not.toBeInTheDocument()
  })

  it('acknowledge mutation success refetches the anomalies list', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { anomalies: MOCK_ANOMALIES } })
    mockPost.mockResolvedValue({ data: { message: 'ANOMALY_ACKNOWLEDGED' } })
    render(<AnomalyAlerts />, { wrapper })

    await screen.findByText('DUPLICATE PAYMENT')
    const ackButtons = screen.getAllByRole('button', { name: /acknowledge/i })
    await user.click(ackButtons[0])

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/cfo/anomalies/an-1/acknowledge'))
    // invalidateQueries triggers a refetch of the same queryKey
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
  })

  it('acknowledge mutation error does not crash the page and re-enables the button', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { anomalies: MOCK_ANOMALIES } })
    mockPost.mockRejectedValue(new Error('network'))
    render(<AnomalyAlerts />, { wrapper })

    await screen.findByText('DUPLICATE PAYMENT')
    const ackButtons = screen.getAllByRole('button', { name: /acknowledge/i })
    await user.click(ackButtons[0])

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    await waitFor(() => expect(ackButtons[0]).not.toBeDisabled())
    expect(screen.getByText('DUPLICATE PAYMENT')).toBeInTheDocument()
  })

  it('disables the acknowledge button while the mutation is pending', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { anomalies: MOCK_ANOMALIES } })
    mockPost.mockReturnValue(new Promise(() => {}))
    render(<AnomalyAlerts />, { wrapper })

    await screen.findByText('DUPLICATE PAYMENT')
    const ackButtons = screen.getAllByRole('button', { name: /acknowledge/i })
    await user.click(ackButtons[0])

    await waitFor(() => expect(ackButtons[0]).toBeDisabled())
  })
})
