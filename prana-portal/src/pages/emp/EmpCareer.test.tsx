import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpCareer } from './EmpCareer'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = {
  employers: [
    { tenant_id: 't1', tenant_name: 'TechCorp', doj: '2020-01-01', dol: null, designation: 'Engineer' },
    { tenant_id: 't2', tenant_name: 'OldCo', doj: '2017-01-01', dol: '2019-12-31', designation: 'Analyst' },
  ],
}
const CAREER = { events: [] }
const DOCS = {
  documents: [
    { document_id: 'd1', tenant_id: 't1', doc_type: 'APPOINTMENT_LETTER', doc_period: null },
    { document_id: 'd2', tenant_id: 't2', doc_type: 'RELIEVING_LETTER', doc_period: null },
  ],
}

function mockAllEndpoints({ profile = PROFILE, career = CAREER, docs = DOCS } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/profile') return Promise.resolve({ data: profile })
    if (url === '/v1/vault/career') return Promise.resolve({ data: career })
    if (url === '/v1/vault/documents') return Promise.resolve({ data: docs })
    return Promise.reject(new Error('unexpected url: ' + url))
  })
}

beforeEach(() => vi.clearAllMocks())

describe('EmpCareer', () => {
  it('shows a loading skeleton while career data is being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpCareer />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an empty state when there are no employers', async () => {
    mockAllEndpoints({ profile: { employers: [] } })
    render(<EmpCareer />, { wrapper })
    expect(await screen.findByText('No employers linked yet')).toBeInTheDocument()
  })

  it('renders the career timeline title, banner, and employer cards', async () => {
    mockAllEndpoints()
    render(<EmpCareer />, { wrapper })

    expect(await screen.findByText('TechCorp')).toBeInTheDocument()
    expect(screen.getByText('Career Timeline')).toBeInTheDocument()
    expect(screen.getByText('Your entire career — verified, assembled automatically from employer-pushed documents')).toBeInTheDocument()
    expect(screen.getByText('AI-assembled.')).toBeInTheDocument()
    expect(screen.getByText('OldCo')).toBeInTheDocument()
  })

  it('marks the current employer Active and the past employer Alumni', async () => {
    mockAllEndpoints()
    render(<EmpCareer />, { wrapper })
    await screen.findByText('TechCorp')
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Alumni')).toBeInTheDocument()
  })

  it('synthesizes a JOINED event from an appointment letter when no career events exist', async () => {
    mockAllEndpoints()
    render(<EmpCareer />, { wrapper })
    await screen.findByText('TechCorp')
    expect(screen.getAllByText('JOINED').length).toBeGreaterThan(0)
  })

  it('shows a footer summary with employer and document counts', async () => {
    mockAllEndpoints()
    render(<EmpCareer />, { wrapper })
    await screen.findByText('TechCorp')
    expect(screen.getByText(/2 employers · 2 documents/)).toBeInTheDocument()
  })

  it('never renders a raw rupee figure anywhere in the career view — privacy contract', async () => {
    mockAllEndpoints()
    render(<EmpCareer />, { wrapper })
    await screen.findByText('TechCorp')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
