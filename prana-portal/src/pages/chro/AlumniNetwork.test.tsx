/**
 * AlumniNetwork tests
 *
 * Contract under test:
 *  GET /v1/alumni/org/list (browse tab, filtered by city/designation_contains)
 *  GET /v1/alumni/org/outreach (messages tab, enabled only when tab==='messages')
 *  POST /v1/alumni/org/outreach (compose + send)
 *
 *  1. Loading skeleton on browse tab
 *  2. Error state on browse tab
 *  3. Empty state ("no consented alumni yet") with guidance copy
 *  4. Renders alumni cards: name, designation, city, tenure, contact (mobile/email or "not shared")
 *  5. Filters (city, designation) included in the query key / request params
 *  6. Switching to "messages" tab triggers the outreach query (enabled: false until then)
 *  7. Messages tab empty state
 *  8. Messages tab renders sent outreach rows
 *  9. Compose modal opens, send button disabled until subject+body filled
 *  10. Successful send shows confirmation and invalidates queries
 *  11. Failed send shows the server error message returned in response.data.detail
 *  12. Download CSV navigates via window.location.href with correct query params
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { AlumniNetwork } from './AlumniNetwork'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const ALUM_A = {
  employee_uuid: 'e-1',
  full_name: 'Priya Sharma',
  designation: 'Software Engineer',
  department: 'Engineering',
  grade: 'L3',
  city: 'Bengaluru',
  doj: '01 Jun 2020',
  dol: '30 Apr 2026',
  tenure_band: '5-6 yrs',
  time_since_exit: '2 months ago',
  mobile: '+919000000001',
  email: 'priya@example.com',
  last_outreach_status: null,
  last_outreach_at: null,
}

const ALUM_B = {
  employee_uuid: 'e-2',
  full_name: 'Ravi Kumar',
  designation: 'Product Manager',
  department: 'Product',
  grade: 'L4',
  city: '',
  doj: '01 Jan 2018',
  dol: '01 Jan 2026',
  tenure_band: '7-8 yrs',
  time_since_exit: '6 months ago',
  mobile: null,
  email: null,
  last_outreach_status: 'SENT',
  last_outreach_at: '2026-06-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom throws "navigation not implemented" if we let real assignment happen
  delete (window as any).location
  ;(window as any).location = { href: '' }
})

describe('AlumniNetwork — browse tab', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AlumniNetwork />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders title, subtitle, and consent notice', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AlumniNetwork />, { wrapper })
    expect(screen.getByText('Alumni Network')).toBeInTheDocument()
    expect(screen.getByText('Former employees who have opted in to stay connected with your org')).toBeInTheDocument()
    expect(screen.getByText(/Only employees who have explicitly opted in/)).toBeInTheDocument()
  })

  it('shows error state on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Failed to load alumni')
  })

  it('shows empty state with guidance copy when there are no alumni', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('No consented alumni yet')
    expect(screen.getByText(/Alumni Connect/)).toBeInTheDocument()
  })

  it('renders alumni cards with contact details when shared, and "not shared" when null', async () => {
    mockGet.mockResolvedValue({ data: { items: [ALUM_A, ALUM_B] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    expect(screen.getByText('+919000000001')).toBeInTheDocument()
    expect(screen.getByText('priya@example.com')).toBeInTheDocument()

    expect(screen.getByText('Ravi Kumar')).toBeInTheDocument()
    const notSharedTexts = screen.getAllByText('Not shared by employee')
    expect(notSharedTexts).toHaveLength(2) // mobile + email for Ravi
  })

  it('shows last outreach status badge when present', async () => {
    mockGet.mockResolvedValue({ data: { items: [ALUM_A, ALUM_B] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Ravi Kumar')
    expect(screen.getByText('SENT')).toBeInTheDocument()
  })

  it('includes filters in the list request params', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.type(screen.getByPlaceholderText('All cities'), 'Bengaluru')

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/v1/alumni/org/list', {
      params: expect.objectContaining({ city: 'Bengaluru', limit: 200 }),
    }))
  })

  it('downloads CSV via window.location.href with current filters', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.type(screen.getByPlaceholderText('All cities'), 'Pune')
    await user.click(screen.getByRole('button', { name: /download csv/i }))

    expect(window.location.href).toBe('/v1/alumni/org/download?city=Pune')
  })
})

describe('AlumniNetwork — messages tab', () => {
  it('does not fetch outreach data until the messages tab is selected', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('No consented alumni yet')
    expect(mockGet).not.toHaveBeenCalledWith('/v1/alumni/org/outreach')
  })

  it('fetches and shows empty state on the messages tab', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/alumni/org/outreach') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: { items: [] } })
    })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('No consented alumni yet')

    await user.click(screen.getByRole('button', { name: /sent messages/i }))
    await screen.findByText('No in-app messages sent yet')
  })

  it('renders sent outreach rows', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/alumni/org/outreach') {
        return Promise.resolve({
          data: {
            items: [{
              outreach_id: 'o-1',
              employee_uuid: 'e-1',
              full_name: 'Priya Sharma',
              designation: 'Software Engineer',
              subject: 'Reconnect?',
              status: 'READ',
              sent_at: '2026-06-15T00:00:00Z',
              read_at: null,
              replied_at: null,
            }],
          },
        })
      }
      return Promise.resolve({ data: { items: [] } })
    })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('No consented alumni yet')

    await user.click(screen.getByRole('button', { name: /sent messages/i }))
    await screen.findByText('Reconnect?')
    expect(screen.getByText('READ')).toBeInTheDocument()
  })
})

describe('AlumniNetwork — compose modal', () => {
  it('opens compose modal, disables send until subject and body are filled', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.click(screen.getByRole('button', { name: /in-app message/i }))
    await screen.findByText('Send in-app message')

    const sendBtn = screen.getByRole('button', { name: /^send$/i })
    expect(sendBtn).toBeDisabled()

    await user.type(screen.getByPlaceholderText(/exciting opportunity/i), 'Hello')
    expect(sendBtn).toBeDisabled()

    await user.type(screen.getByPlaceholderText(/write a personalised message/i), 'Would love to reconnect')
    expect(sendBtn).not.toBeDisabled()
  })

  it('sends outreach successfully and shows confirmation', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.click(screen.getByRole('button', { name: /in-app message/i }))
    await screen.findByText('Send in-app message')
    await user.type(screen.getByPlaceholderText(/exciting opportunity/i), 'Hello')
    await user.type(screen.getByPlaceholderText(/write a personalised message/i), 'Would love to reconnect')
    await user.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/alumni/org/outreach', {
      employee_uuid: 'e-1',
      subject: 'Hello',
      body_text: 'Would love to reconnect',
    }))
    await screen.findByText('Message sent ✓')
  })

  it('shows the server-provided error message when send fails', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    mockPost.mockRejectedValue({ response: { data: { detail: 'Employee has opted out of outreach' } } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.click(screen.getByRole('button', { name: /in-app message/i }))
    await screen.findByText('Send in-app message')
    await user.type(screen.getByPlaceholderText(/exciting opportunity/i), 'Hello')
    await user.type(screen.getByPlaceholderText(/write a personalised message/i), 'Would love to reconnect')
    await user.click(screen.getByRole('button', { name: /^send$/i }))

    await screen.findByText('Employee has opted out of outreach')
  })

  it('falls back to a generic error message when the server gives no detail', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    mockPost.mockRejectedValue(new Error('network down'))
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.click(screen.getByRole('button', { name: /in-app message/i }))
    await screen.findByText('Send in-app message')
    await user.type(screen.getByPlaceholderText(/exciting opportunity/i), 'Hello')
    await user.type(screen.getByPlaceholderText(/write a personalised message/i), 'Would love to reconnect')
    await user.click(screen.getByRole('button', { name: /^send$/i }))

    await screen.findByText('Failed to send')
  })

  it('closes the compose modal on Cancel without sending', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { items: [ALUM_A] } })
    render(<AlumniNetwork />, { wrapper })
    await screen.findByText('Priya Sharma')

    await user.click(screen.getByRole('button', { name: /in-app message/i }))
    await screen.findByText('Send in-app message')
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.queryByText('Send in-app message')).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
