import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PaNotificationLog } from './PaNotificationLog'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  items: [
    {
      notification_id: 'n-1', created_at: '2026-07-01T10:00:00Z', tenant_id: 'tenant-uuid-abcdefgh',
      event_type: 'ANOMALY_DETECTED', channel: 'EMAIL', recipient_email: 'oa@acme.example',
      template_id: 'ANOMALY_TPL', status: 'SENT', retry_count: 0, error_message: null,
    },
    {
      notification_id: 'n-2', created_at: '2026-07-02T10:00:00Z', tenant_id: null,
      event_type: 'DOCUMENT_ROUTED', channel: 'SMS', recipient_phone: '+919000000001',
      template_id: 'DOC_ROUTED_TPL', status: 'FAILED', retry_count: 2, error_message: 'Provider timeout',
    },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('PaNotificationLog', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<PaNotificationLog />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state on failure', async () => {
    mockGet.mockRejectedValue(new Error('down'))
    render(<PaNotificationLog />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load notification log.')).toBeInTheDocument())
  })

  it('shows empty state when no rows', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<PaNotificationLog />, { wrapper })
    await waitFor(() => expect(screen.getByText('No notifications match this filter.')).toBeInTheDocument())
  })

  it('renders notification rows and delivery summary', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PaNotificationLog />, { wrapper })
    await waitFor(() => expect(screen.getByText('oa@acme.example')).toBeInTheDocument())
    expect(screen.getByText('Provider timeout')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('ANOMALY_DETECTED')).toBeInTheDocument()
  })

  it('refetches with tenant filter applied', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PaNotificationLog />, { wrapper })
    await waitFor(() => expect(screen.getByText('oa@acme.example')).toBeInTheDocument())
    const input = screen.getByPlaceholderText('Tenant UUID…')
    await user.type(input, 'tenant-uuid-abcdefgh')
    await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith(expect.stringContaining('tenant_id=tenant-uuid-abcdefgh')))
  })
})
