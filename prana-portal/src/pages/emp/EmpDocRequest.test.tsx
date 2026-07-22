import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpDocRequest } from './EmpDocRequest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = { employers: [{ tenant_id: 't1', tenant_name: 'TechCorp' }] }

interface DocRequest {
  doc_type: string; period: string; status: string; tenant_name: string
  requested_at: string; fulfilled_at?: string
}
interface Requests { requests: DocRequest[] }

function mockAllEndpoints({ profile = PROFILE, requests = { requests: [] } as Requests } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/profile') return Promise.resolve({ data: profile })
    if (url === '/v1/vault/requests') return Promise.resolve({ data: requests })
    return Promise.reject(new Error('unexpected url: ' + url))
  })
}

beforeEach(() => vi.clearAllMocks())

describe('EmpDocRequest', () => {
  it('renders the title, sub, and new-request form', async () => {
    mockAllEndpoints()
    render(<EmpDocRequest />, { wrapper })
    expect(screen.getByText('Request Documents')).toBeInTheDocument()
    expect(screen.getByText('Formally request missing documents from your employers — tracked and timestamped')).toBeInTheDocument()
    expect(screen.getByText('New Request')).toBeInTheDocument()
  })

  it('shows an empty state in request history when there are no requests', async () => {
    mockAllEndpoints()
    render(<EmpDocRequest />, { wrapper })
    expect(await screen.findByText('No requests sent yet.')).toBeInTheDocument()
  })

  it('populates the employer dropdown from profile data', async () => {
    mockAllEndpoints()
    render(<EmpDocRequest />, { wrapper })
    expect(await screen.findByRole('option', { name: 'TechCorp' })).toBeInTheDocument()
  })

  it('disables Send Request until employer and doc type are chosen', async () => {
    mockAllEndpoints()
    const user = userEvent.setup()
    render(<EmpDocRequest />, { wrapper })
    await screen.findByRole('option', { name: 'TechCorp' })

    const sendBtn = screen.getByRole('button', { name: 'Send Request' })
    expect(sendBtn).toBeDisabled()

    const [employerSelect, docTypeSelect] = screen.getAllByRole('combobox')
    await user.selectOptions(employerSelect, 't1')
    expect(sendBtn).toBeDisabled()

    await user.selectOptions(docTypeSelect, 'FORM_16')
    expect(sendBtn).toBeEnabled()
  })

  it('submits a document request and shows the tracking-id toast', async () => {
    mockAllEndpoints()
    mockPost.mockResolvedValue({ data: { doc_request_id: 'abcdef1234567890' } })
    const user = userEvent.setup()
    render(<EmpDocRequest />, { wrapper })
    await screen.findByRole('option', { name: 'TechCorp' })

    const [employerSelect, docTypeSelect] = screen.getAllByRole('combobox')
    await user.selectOptions(employerSelect, 't1')
    await user.selectOptions(docTypeSelect, 'FORM_16')
    await user.click(screen.getByRole('button', { name: 'Send Request' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/vault/requests', {
      tenant_id: 't1', doc_type: 'FORM_16', period: '', note: '',
    }))
    expect(await screen.findByText('📨 Formal request sent — tracking ID: REQ-ABCDEF12')).toBeInTheDocument()
  })

  it('shows a failure toast when the request submission fails', async () => {
    mockAllEndpoints()
    mockPost.mockRejectedValue(new Error('network'))
    const user = userEvent.setup()
    render(<EmpDocRequest />, { wrapper })
    await screen.findByRole('option', { name: 'TechCorp' })

    const [employerSelect, docTypeSelect] = screen.getAllByRole('combobox')
    await user.selectOptions(employerSelect, 't1')
    await user.selectOptions(docTypeSelect, 'FORM_16')
    await user.click(screen.getByRole('button', { name: 'Send Request' }))

    expect(await screen.findByText('Request failed. Try again.')).toBeInTheDocument()
  })

  it('renders existing request history with fulfilled and pending status badges', async () => {
    mockAllEndpoints({
      requests: {
        requests: [
          { doc_type: 'FORM_16', period: '2023', status: 'FULFILLED', tenant_name: 'TechCorp', requested_at: '2024-01-01T00:00:00Z', fulfilled_at: '2024-01-05T00:00:00Z' },
          { doc_type: 'SALARY_SLIP', period: '2024-01', status: 'PENDING', tenant_name: 'TechCorp', requested_at: '2024-01-01T00:00:00Z' },
        ],
      },
    })
    render(<EmpDocRequest />, { wrapper })

    expect(await screen.findByText('Fulfilled')).toBeInTheDocument()
    expect(screen.getByText(/Pending ·/)).toBeInTheDocument()
  })

  it('never renders a raw rupee figure anywhere on the doc request page — privacy contract', async () => {
    mockAllEndpoints()
    render(<EmpDocRequest />, { wrapper })
    await screen.findByRole('option', { name: 'TechCorp' })
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
