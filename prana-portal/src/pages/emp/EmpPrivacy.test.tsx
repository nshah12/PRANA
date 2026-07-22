import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpPrivacy } from './EmpPrivacy'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = { employer_count: 2 }
const ACTIVITY = { access_log: [{ via_share: false, employer_name: 'TechCorp' as string | null, access_type: 'VIEW', doc_type: 'SALARY_SLIP', accessed_at: '2024-01-01T00:00:00Z' }] }
const SHARES = { shares: [{ token_id: 's1' }] }
const DOCS = { documents: [{ doc_type: 'FORM_16', doc_period: '2023' }], count: 1 }

function mockAllEndpoints({ profile = PROFILE, activity = ACTIVITY, shares = SHARES, docs = DOCS } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/profile') return Promise.resolve({ data: profile })
    if (url === '/v1/vault/activity') return Promise.resolve({ data: activity })
    if (url === '/v1/vault/share') return Promise.resolve({ data: shares })
    if (url === '/v1/vault/documents') return Promise.resolve({ data: docs })
    return Promise.reject(new Error('unexpected url: ' + url))
  })
}

beforeEach(() => vi.clearAllMocks())

describe('EmpPrivacy', () => {
  it('shows a loading skeleton while data is being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpPrivacy />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders the privacy cockpit title, sub, and stat cards', async () => {
    mockAllEndpoints()
    render(<EmpPrivacy />, { wrapper })

    expect(await screen.findByText('Privacy Cockpit')).toBeInTheDocument()
    expect(screen.getByText('Complete transparency over how your data has moved — ever')).toBeInTheDocument()
    expect(screen.getByText('Linked Employers')).toBeInTheDocument()
    expect(screen.getByText('Docs in Vault')).toBeInTheDocument()
    expect(screen.getByText('Active Shares')).toBeInTheDocument()
  })

  it('shows empty states for access log and AI extraction log when there is no data', async () => {
    mockAllEndpoints({ activity: { access_log: [] }, docs: { documents: [], count: 0 } })
    render(<EmpPrivacy />, { wrapper })

    expect(await screen.findByText('No access events yet.')).toBeInTheDocument()
    expect(screen.getByText('No documents extracted yet.')).toBeInTheDocument()
  })

  it('renders access log entries distinguishing OA vs C-Share access', async () => {
    mockAllEndpoints({
      activity: {
        access_log: [
          { via_share: false, employer_name: 'TechCorp', access_type: 'VIEW', doc_type: 'SALARY_SLIP', accessed_at: '2024-01-01T00:00:00Z' },
          { via_share: true, employer_name: null, access_type: 'VIEW', doc_type: 'FORM_16', accessed_at: '2024-01-02T00:00:00Z' },
        ],
      },
    })
    render(<EmpPrivacy />, { wrapper })

    expect(await screen.findByText('OA · TechCorp')).toBeInTheDocument()
    expect(screen.getByText('C-Share: Recipient')).toBeInTheDocument()
  })

  it('renders the AI extraction log with the PAN-never-stored footer note', async () => {
    mockAllEndpoints()
    render(<EmpPrivacy />, { wrapper })

    await screen.findByText('AI Extraction Log')
    expect(screen.getByText('Fields extracted · PAN destroyed in 2ms')).toBeInTheDocument()
    expect(screen.getByText('Your PAN is never stored. Every extraction confirms destruction within 2ms.')).toBeInTheDocument()
  })

  it('never renders a raw rupee figure or PAN-shaped value anywhere — privacy contract', async () => {
    mockAllEndpoints()
    render(<EmpPrivacy />, { wrapper })
    await screen.findByText('Privacy Cockpit')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
