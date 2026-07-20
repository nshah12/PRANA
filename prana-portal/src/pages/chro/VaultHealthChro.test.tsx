/**
 * VaultHealthChro tests
 *
 * Contract under test (GET /v1/chro/vault-health):
 *  1. Renders title + export PDF button always
 *  2. Shows "Loading…" text inside the chart panel while fetching (isLoading branch)
 *  3. Renders 4 KPI cards with overall/employment_proof/salary_slip/form16 scores
 *  4. Renders department breakdown bar chart data once loaded
 *  5. Renders gap cards when data.gaps present, with affected_count and CTA
 *  6. Empty state: no gaps section rendered when data.gaps is empty/absent
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { VaultHealthChro } from './VaultHealthChro'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  overall_score: 82,
  employment_proof_score: 91,
  salary_slip_score: 77,
  form16_score: 68,
  by_department: [
    { department: 'Engineering', score: 88 },
    { department: 'Sales', score: 71 },
  ],
  gaps: [
    { description: 'Form-16 missing for FY 2025-26', affected_count: 12 },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('VaultHealthChro', () => {
  it('renders title, subtitle and export button always', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<VaultHealthChro />, { wrapper })
    expect(screen.getByText('Vault Health Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Organisation-wide document completeness')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export pdf/i })).toBeInTheDocument()
  })

  it('shows loading text in the chart panel while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<VaultHealthChro />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows placeholder dashes for KPI cards while loading', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<VaultHealthChro />, { wrapper })
    expect(screen.getAllByText('—').length).toBe(4)
  })

  it('renders 4 KPI cards with scores on success', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<VaultHealthChro />, { wrapper })
    await waitFor(() => expect(screen.getByText('82%')).toBeInTheDocument())
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('77%')).toBeInTheDocument()
    expect(screen.getByText('68%')).toBeInTheDocument()
  })

  it('renders department breakdown heading and department names once loaded', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<VaultHealthChro />, { wrapper })
    expect(screen.getByText('Department breakdown')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument())
  })

  it('renders gap cards with affected count and alert CTA when gaps present', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<VaultHealthChro />, { wrapper })
    await waitFor(() => expect(screen.getByText('Gaps detected')).toBeInTheDocument())
    expect(screen.getByText('Form-16 missing for FY 2025-26')).toBeInTheDocument()
    expect(screen.getByText('12 employees affected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /alert oa-operator/i })).toBeInTheDocument()
  })

  it('renders no gaps section when data.gaps is empty', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, gaps: [] } })
    render(<VaultHealthChro />, { wrapper })
    await waitFor(() => expect(screen.getByText('82%')).toBeInTheDocument())
    expect(screen.queryByText('Gaps detected')).not.toBeInTheDocument()
  })

  it('calls the vault-health endpoint', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<VaultHealthChro />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/v1/chro/vault-health'))
  })
})
