/**
 * NotificationLog tests
 *
 *  1. Loading state (no summary line shown yet)
 *  2. Error state with retry
 *  3. Empty state — "No notifications match this filter."
 *  4. Renders rows with delivered/failed counts and table content
 *  5. Filter selects (channel, event type, limit) trigger new query params
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { NotificationLog } from './NotificationLog'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('NotificationLog', () => {
  it('shows loading state (no summary counts yet) while fetching', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<NotificationLog />, { wrapper })
    expect(screen.getByText('Notification Log')).toBeInTheDocument()
    expect(screen.queryByText('delivered')).not.toBeInTheDocument()
  })

  it('shows error state with retry that refetches', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    render(<NotificationLog />, { wrapper })
    expect(await screen.findByText('Failed to load notification log.')).toBeInTheDocument()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    await user.click(screen.getByText('Retry'))
    await waitFor(() => expect(screen.getByText('No notifications match this filter.')).toBeInTheDocument())
  })

  it('shows empty state when there are no notifications', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<NotificationLog />, { wrapper })
    expect(await screen.findByText('No notifications match this filter.')).toBeInTheDocument()
  })

  it('renders delivered/failed summary counts and table rows', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        items: [
          { notification_id: 'n-1', created_at: '2026-07-05T08:00:00Z', event_type: 'ANOMALY_DETECTED', channel: 'EMAIL', recipient_email: 'ciso@acme.example', template_id: 'ANOMALY_TMPL', status: 'SENT', retry_count: 0 },
          { notification_id: 'n-2', created_at: '2026-07-05T09:00:00Z', event_type: 'ACCOUNT_LOCKED', channel: 'SMS', recipient_phone: '+919000000001', template_id: 'LOCK_TMPL', status: 'FAILED', retry_count: 2, error_message: 'Timeout' },
        ],
      },
    })
    render(<NotificationLog />, { wrapper })
    // "1 delivered" / "1 failed / bounced" are split across sibling text nodes
    // (`{count} {label}`) inside a shared <span> — match on the span's full text content
    // (trimmed, since the icon + JSX whitespace leaves a leading space).
    expect(await screen.findByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.trim() === '1 delivered')).toBeInTheDocument()
    expect(screen.getByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.trim() === '1 failed / bounced')).toBeInTheDocument()
    expect(screen.getByText('2 total shown')).toBeInTheDocument()
    // 'ANOMALY_DETECTED' also appears as an <option> in the event-type filter select —
    // scope to the table cell specifically.
    expect(screen.getByText('ANOMALY_DETECTED', { selector: 'td' })).toBeInTheDocument()
    expect(screen.getByText('ciso@acme.example')).toBeInTheDocument()
    expect(screen.getByText('+919000000001')).toBeInTheDocument()
    expect(screen.getByText('Timeout')).toBeInTheDocument()
  })

  it('refetches with the selected channel filter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<NotificationLog />, { wrapper })
    await screen.findByText('No notifications match this filter.')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[0], 'EMAIL')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/notification-log?limit=50&channel=EMAIL'))
  })

  it('refetches with the selected event type filter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<NotificationLog />, { wrapper })
    await screen.findByText('No notifications match this filter.')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[1], 'DOCUMENT_ROUTED')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/notification-log?limit=50&event_type=DOCUMENT_ROUTED'))
  })

  it('refetches with the selected limit', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } })
    render(<NotificationLog />, { wrapper })
    await screen.findByText('No notifications match this filter.')
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[2], '100')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/ciso/notification-log?limit=100'))
  })
})
