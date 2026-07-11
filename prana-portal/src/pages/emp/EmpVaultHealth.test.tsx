import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpVaultHealth } from './EmpVaultHealth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = {
  employers: [
    { tenant_id: 't1', tenant_name: 'TechCorp', doj: '2020-01-01', dol: null },
    { tenant_id: 't2', tenant_name: 'OldCo', doj: '2017-01-01', dol: '2019-12-31' },
  ],
}

interface GapDetail { description: string; employer: string }
interface Health { overall_score: number; gap_count: number; gap_detail: GapDetail[] }
interface Doc { tenant_id: string; doc_type: string; doc_period: string | null }
interface Docs { documents: Doc[] }

function mockAllEndpoints({
  health = { overall_score: 0, gap_count: 0, gap_detail: [] } as Health,
  profile = PROFILE,
  docs = { documents: [] } as Docs,
} = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/health') return Promise.resolve({ data: health })
    if (url === '/v1/vault/profile') return Promise.resolve({ data: profile })
    if (url === '/v1/vault/documents') return Promise.resolve({ data: docs })
    return Promise.reject(new Error('unexpected url: ' + url))
  })
}

beforeEach(() => vi.clearAllMocks())

describe('EmpVaultHealth', () => {
  it('shows a loading skeleton while health data is being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpVaultHealth />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders the title, sub, and score breakdown section', async () => {
    mockAllEndpoints()
    render(<EmpVaultHealth />, { wrapper })

    expect(await screen.findByText('Score Breakdown')).toBeInTheDocument()
    expect(screen.getByText('Vault Health')).toBeInTheDocument()
    expect(screen.getByText('Document completeness across all your employers')).toBeInTheDocument()
    expect(screen.getByText('Vault Health Score')).toBeInTheDocument()
  })

  it('marks all breakdown rows Missing when the vault has zero documents', async () => {
    mockAllEndpoints({ docs: { documents: [] } })
    render(<EmpVaultHealth />, { wrapper })

    await screen.findByText('Employment Proof')
    expect(screen.getAllByText('✗ Missing').length).toBeGreaterThan(0)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('marks Employment Proof Complete when an appointment letter exists', async () => {
    mockAllEndpoints({
      docs: { documents: [{ tenant_id: 't1', doc_type: 'APPOINTMENT_LETTER', doc_period: null }] },
    })
    render(<EmpVaultHealth />, { wrapper })

    await screen.findByText('Employment Proof')
    const row = screen.getByText('Employment Proof').closest('div')!
    expect(row.textContent).toContain('✓ Complete')
  })

  it('shows the "vault is complete" success state when there are no gaps and score > 0', async () => {
    // Salary slips must fall within the last 12 months of "now" to count as recent —
    // build periods relative to the current date rather than a hardcoded year.
    const now = new Date()
    const recentPeriods = Array.from({ length: 6 }, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    })
    mockAllEndpoints({
      health: { overall_score: 100, gap_count: 0, gap_detail: [] },
      profile: { employers: [{ tenant_id: 't1', tenant_name: 'TechCorp', doj: '2020-01-01', dol: null }] },
      docs: {
        documents: [
          { tenant_id: 't1', doc_type: 'APPOINTMENT_LETTER', doc_period: null },
          { tenant_id: 't1', doc_type: 'FORM_16', doc_period: '2023' },
          ...recentPeriods.map(p => ({ tenant_id: 't1', doc_type: 'SALARY_SLIP', doc_period: p })),
        ],
      },
    })
    render(<EmpVaultHealth />, { wrapper })

    expect(await screen.findByText('Vault is complete')).toBeInTheDocument()
    expect(screen.getByText('No gaps detected across all employers.')).toBeInTheDocument()
  })

  it('shows gap cards with a request action when gaps are present from the API', async () => {
    mockAllEndpoints({
      health: {
        overall_score: 40, gap_count: 1,
        gap_detail: [{ description: 'Form-16 missing for FY2022-23', employer: 'TechCorp' }],
      },
    })
    render(<EmpVaultHealth />, { wrapper })

    expect(await screen.findByText(/Form-16 missing for FY2022-23/)).toBeInTheDocument()
    expect(screen.getByText('Gaps Found — Action Required')).toBeInTheDocument()
    expect(screen.getAllByText('Request →').length).toBeGreaterThan(0)
  })

  it('flags historic salary slips missing for alumni employers', async () => {
    mockAllEndpoints({
      profile: { employers: [{ tenant_id: 't2', tenant_name: 'OldCo', doj: '2017-01-01', dol: '2019-12-31' }] },
      docs: { documents: [] },
    })
    render(<EmpVaultHealth />, { wrapper })

    expect(await screen.findByText('🗂 Salary slips missing from past employer(s)')).toBeInTheDocument()
    expect(screen.getByText('Self-Upload →')).toBeInTheDocument()
  })

  it('never renders a raw rupee figure anywhere in the vault health view — privacy contract', async () => {
    mockAllEndpoints()
    render(<EmpVaultHealth />, { wrapper })
    await screen.findByText('Score Breakdown')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
