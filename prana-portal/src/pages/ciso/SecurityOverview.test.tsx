/**
 * SecurityOverview tests
 *
 *  1. Loading skeleton
 *  2. Error state with retry
 *  3. Renders posture card (GREEN/RED), stat values, and threat feed
 *  4. Empty threat feed state
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SecurityOverview } from './SecurityOverview'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('SecurityOverview', () => {
  it('shows loading skeleton while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<SecurityOverview />, { wrapper })
    expect(screen.queryByText('Security Overview')).not.toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<SecurityOverview />, { wrapper })
    expect(await screen.findByText('Failed to load security overview.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { posture: 'GREEN', threats: [] } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('Security Overview')).toBeInTheDocument())
  })

  it('renders a GREEN posture and stat values', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        posture: 'GREEN',
        threats_24h: 0,
        anomalies_open: 3,
        auth_events_24h: 142,
        event_timeline: [{ date: '2026-07-01', events: 2 }],
        threats: [],
      },
    })
    render(<SecurityOverview />, { wrapper })
    expect(await screen.findByText('GREEN')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('142')).toBeInTheDocument()
    expect(screen.getByText('No active threats.')).toBeInTheDocument()
  })

  it('renders a RED posture with live threat feed entries', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        posture: 'RED',
        threats_24h: 5,
        anomalies_open: 8,
        auth_events_24h: 300,
        event_timeline: [],
        threats: [
          { severity: 'HIGH', description: 'Bulk download detected from unusual IP', detected_at: '2026-07-05T10:00:00Z' },
        ],
      },
    })
    render(<SecurityOverview />, { wrapper })
    expect(await screen.findByText('RED')).toBeInTheDocument()
    expect(screen.getByText('Bulk download detected from unusual IP')).toBeInTheDocument()
  })
})
