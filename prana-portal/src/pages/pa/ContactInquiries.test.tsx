import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ContactInquiries } from './ContactInquiries'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const CONTACTS = {
  items: [
    {
      id: 'c-1', name: 'Rahul Mehta', email: 'rahul@example.in', org: 'Acme Ltd',
      enquiry_type: 'Product demo', status: 'NEW', submitted_at: '2026-07-01T10:00:00Z',
      message: 'We would like a demo of PRANA.',
    },
  ],
}

const APPLICATIONS = {
  items: [
    {
      id: 'a-1', org_name: 'PQRS Fintech', domain: 'pqrsfintech.in', contact_email: 'admin@pqrsfintech.in',
      contact_name: 'Sunita Rao', contact_mobile: '+919000000000', entity_type: 'PRIVATE_LIMITED',
      industry: 'BFSI', headcount_band: '201-500', how_heard: 'Referral', agreed_to_dpa: true,
      email_verified: true, status: 'PENDING', submitted_at: '2026-07-02T10:00:00Z', message: 'Interested in onboarding.',
      review_notes: null,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockImplementation((url: string) => {
    if (url.includes('contact-inquiries')) return Promise.resolve({ data: CONTACTS })
    if (url.includes('org-applications')) return Promise.resolve({ data: APPLICATIONS })
    return Promise.resolve({ data: { items: [] } })
  })
})

describe('ContactInquiries', () => {
  it('renders the contact messages tab by default', async () => {
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    expect(screen.getByText('Inquiries & Registrations')).toBeInTheDocument()
  })

  it('shows empty state when there are no contact messages', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('contact-inquiries')) return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: APPLICATIONS })
    })
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('No contact messages yet')).toBeInTheDocument())
  })

  it('expands a contact message to show its body and reply link', async () => {
    const user = userEvent.setup()
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    await user.click(screen.getByText('Rahul Mehta'))
    expect(await screen.findByText('We would like a demo of PRANA.')).toBeInTheDocument()
    expect(screen.getByText('Reply by email →')).toBeInTheDocument()
  })

  it('switches to the registrations tab and shows applications', async () => {
    const user = userEvent.setup()
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    await user.click(screen.getByText('Self-service registrations'))
    expect(await screen.findByText('PQRS Fintech')).toBeInTheDocument()
  })

  it('shows empty state for registrations when there are none', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) => {
      if (url.includes('org-applications')) return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: CONTACTS })
    })
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    await user.click(screen.getByText('Self-service registrations'))
    expect(await screen.findByText('No self-service applications yet')).toBeInTheDocument()
  })

  it('reviews a pending application as REVIEWED', async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    await user.click(screen.getByText('Self-service registrations'))
    await user.click(await screen.findByText('PQRS Fintech'))
    await user.click(screen.getByText('Mark reviewed'))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/org-applications/a-1', { status: 'REVIEWED', review_notes: '' }))
  })

  it('rejects a pending application', async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<ContactInquiries />, { wrapper })
    await waitFor(() => expect(screen.getByText('Rahul Mehta')).toBeInTheDocument())
    await user.click(screen.getByText('Self-service registrations'))
    await user.click(await screen.findByText('PQRS Fintech'))
    await user.click(screen.getByText('Reject'))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/org-applications/a-1', { status: 'REJECTED', review_notes: '' }))
  })
})
