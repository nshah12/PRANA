/**
 * CompliancePosture tests
 *
 * Contract under test (GET /v1/chro/compliance-posture):
 *  1. Loading skeleton while fetching
 *  2. Error state with retry button on failure; retry re-invokes the query
 *  3. Overall risk badge renders with correct severity styling
 *  4. Score cards render consent/vault/erasure/grievance percentages
 *  5. DPDP checklist renders requirement, statutory_ref, note, status per item
 *  6. Empty checklist shows the loading/empty placeholder copy
 *  7. Action items render description, risk, and due date
 *  8. Empty action items shows "No open action items."
 */
import { render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { CompliancePosture } from './CompliancePosture'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

const MOCK = {
  overall_risk: 'MEDIUM',
  consent_pct: 92,
  vault_completeness_pct: 81,
  erasure_sla_pct: 100,
  grievance_resolved_pct: 88,
  checklist: [
    { requirement: 'Consent captured before processing', statutory_ref: 'DPDP Sec 6', status: 'COMPLIANT', note: null },
    { requirement: 'Erasure requests resolved within SLA', statutory_ref: 'DPDP Sec 12', status: 'ACTION_NEEDED', note: '2 requests overdue' },
  ],
  action_items: [
    { description: 'Resolve overdue erasure request for EMP-4821', risk: 'HIGH', due_date: '2026-07-15T00:00:00Z' },
  ],
}

describe('CompliancePosture', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CompliancePosture />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders title and subtitle', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<CompliancePosture />, { wrapper })
    expect(screen.getByText('Compliance Posture')).toBeInTheDocument()
    expect(screen.getByText('DPDP Act 2023 · 7-year audit retention')).toBeInTheDocument()
  })

  it('shows error state with retry button on failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Failed to load compliance posture.')
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('re-invokes the query when retry is clicked', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValue(new Error('network'))
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Failed to load compliance posture.')

    mockGet.mockResolvedValueOnce({ data: MOCK })
    await user.click(screen.getByRole('button', { name: /retry/i }))
    await screen.findByText('Consent captured before processing')
  })

  it('renders the overall risk badge with correct severity', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(screen.getByText('MEDIUM risk')).toBeInTheDocument()
  })

  it('defaults to LOW risk badge when overall_risk is absent', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, overall_risk: undefined } })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(screen.getByText('LOW risk')).toBeInTheDocument()
  })

  it('renders score cards with percentages and targets', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')

    const consentCard = screen.getByText('Consent coverage').closest<HTMLElement>('div.bg-white')!
    expect(within(consentCard).getByText('92%')).toBeInTheDocument()
    expect(within(consentCard).getByText('target 100%')).toBeInTheDocument()

    const vaultCard = screen.getByText('Vault completeness').closest<HTMLElement>('div.bg-white')!
    expect(within(vaultCard).getByText('81%')).toBeInTheDocument()
    expect(within(vaultCard).getByText('target 90%')).toBeInTheDocument()

    const erasureCard = screen.getByText('Erasure SLA met').closest<HTMLElement>('div.bg-white')!
    expect(within(erasureCard).getByText('100%')).toBeInTheDocument()

    const grievanceCard = screen.getByText('Grievance resolved').closest<HTMLElement>('div.bg-white')!
    expect(within(grievanceCard).getByText('88%')).toBeInTheDocument()
    expect(within(grievanceCard).getByText('target 95%')).toBeInTheDocument()
  })

  it('shows placeholder dashes for score cards when values are null', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, consent_pct: null, vault_completeness_pct: null, erasure_sla_pct: null, grievance_resolved_pct: null } })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(screen.getAllByText('—').length).toBe(4)
  })

  it('renders DPDP checklist items with requirement, ref, status and note', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(screen.getByText('DPDP Act 2023 checklist')).toBeInTheDocument()
    expect(screen.getByText('DPDP Sec 6')).toBeInTheDocument()
    expect(screen.getByText('COMPLIANT')).toBeInTheDocument()

    expect(screen.getByText('Erasure requests resolved within SLA')).toBeInTheDocument()
    expect(screen.getByText('DPDP Sec 12')).toBeInTheDocument()
    expect(screen.getByText('ACTION_NEEDED')).toBeInTheDocument()
    expect(screen.getByText('2 requests overdue')).toBeInTheDocument()
  })

  it('shows checklist placeholder copy when checklist is empty', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, checklist: [] } })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Resolve overdue erasure request for EMP-4821')
    expect(screen.getByText('Checklist loading…')).toBeInTheDocument()
  })

  it('renders action items with description, risk badge, and due date', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Resolve overdue erasure request for EMP-4821')
    expect(screen.getByText('Open action items')).toBeInTheDocument()
    const actionRow = screen.getByText('Resolve overdue erasure request for EMP-4821').closest<HTMLElement>('div.px-5')!
    expect(within(actionRow).getByText('HIGH')).toBeInTheDocument()
    expect(within(actionRow).getByText(/Due /)).toBeInTheDocument()
  })

  it('shows "No open action items." when action_items is empty', async () => {
    mockGet.mockResolvedValue({ data: { ...MOCK, action_items: [] } })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(screen.getByText('No open action items.')).toBeInTheDocument()
  })

  it('calls the compliance-posture endpoint', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<CompliancePosture />, { wrapper })
    await screen.findByText('Consent captured before processing')
    expect(mockGet).toHaveBeenCalledWith('/v1/chro/compliance-posture')
  })
})
