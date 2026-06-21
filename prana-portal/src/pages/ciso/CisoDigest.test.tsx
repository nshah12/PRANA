/**
 * CisoDigest tests — TDD RED → GREEN → REFACTOR
 *
 *  1. Renders DigestDatePicker always (not gated behind loading)
 *  2. Shows loading skeleton while fetching
 *  3. Shows error state with retry button on failure
 *  4. Renders 4 stat cards on success
 *  5. Renders access-by-channel bars when data present
 *  6. Renders incident log when incidents present
 *  7. Severity badge text is visible (High / Medium / Low)
 *  8. Shows "no incidents" success state when anomalies_total = 0
 *  9. Shows open anomalies CTA when anomalies_open > 0
 * 10. API URL includes from/to params
 * 11. Privacy: response text must not contain "pan" or "salary"
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CisoDigest } from './CisoDigest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  from: '2026-06-12', to: '2026-06-19',
  total_accesses: 1847, anomalies_total: 3, anomalies_open: 2,
  force_logouts: 1, share_tokens_period: 34,
  by_channel: [
    { channel: 'MOBILE', count: 1256 },
    { channel: 'PORTAL', count: 591 },
  ],
  incidents: [
    { anomaly_id: 'a1', rule_name: 'BULK_ACCESS', severity: 'HIGH',
      detected_at: '2026-06-15T10:00:00Z', status: 'OPEN', resolved: false },
    { anomaly_id: 'a2', rule_name: 'UNUSUAL_HOUR', severity: 'MEDIUM',
      detected_at: '2026-06-14T22:30:00Z', status: 'RESOLVED', resolved: true },
  ],
}

const MOCK_CLEAN = { ...MOCK, anomalies_total: 0, anomalies_open: 0, incidents: [] }

beforeEach(() => vi.clearAllMocks())

describe('CisoDigest', () => {
  it('renders DigestDatePicker immediately (not gated behind loading)', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CisoDigest />, { wrapper })
    expect(screen.getByRole('button', { name: /this week/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CisoDigest />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<CisoDigest />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    )
  })

  it('renders 4 stat cards on success', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('1847')).toBeInTheDocument())
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('34')).toBeInTheDocument()
  })

  it('renders access-by-channel bars', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('MOBILE')).toBeInTheDocument())
    expect(screen.getByText('PORTAL')).toBeInTheDocument()
  })

  it('renders incident log with severity badge and rule name', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('BULK ACCESS')).toBeInTheDocument())
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('shows Resolved and Open pills on incidents', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('Open')).toBeInTheDocument())
    expect(screen.getByText('Resolved')).toBeInTheDocument()
  })

  it('shows clean state when no anomalies', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK_CLEAN } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/no anomalies or incidents/i)).toBeInTheDocument()
    )
  })

  it('shows open anomalies CTA when anomalies_open > 0', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText(/2 open anomal/i)).toBeInTheDocument())
  })

  it('includes from/to in the API URL', async () => {
    mockGet.mockResolvedValue({ data: { digest: MOCK } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toMatch(/from=\d{4}-\d{2}-\d{2}/)
    expect(url).toMatch(/to=\d{4}-\d{2}-\d{2}/)
  })

  it('privacy: no raw PAN numbers or salary figures in rendered output', async () => {
    // Inject PAN-like and salary-like values into mock to ensure they are never rendered
    const mockWithSensitive = {
      ...MOCK,
      // These fields must NOT appear in the component — if they leak, the test catches it
      _pan: 'ABCDE1234F',
      _salary: '₹85000',
    }
    mockGet.mockResolvedValue({ data: { digest: mockWithSensitive } })
    render(<CisoDigest />, { wrapper })
    await waitFor(() => expect(screen.getByText('1847')).toBeInTheDocument())
    const text = document.body.textContent ?? ''
    // PAN format: 5 letters + 4 digits + 1 letter
    expect(text).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
    // Raw salary rupee figures should not appear
    expect(text).not.toContain('₹85000')
  })
})
