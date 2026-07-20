import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { IncidentPolicyConfig } from './IncidentPolicyConfig'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const SLA_MOCK = {
  items: [
    { severity: 'P0', sla_minutes: 30, auto_create_incident: true, description: 'Critical',
      updated_by: null, updated_at: null },
    { severity: 'P1', sla_minutes: 60, auto_create_incident: true, description: null,
      updated_by: null, updated_at: null },
  ],
}

const RULES_MOCK = {
  items: [
    { rule_id: 'r-1', domain: 'ANOMALY_RULE', match_type: 'EXACT', match_value: 'BULK_DOC_ACCESS',
      occurrence_threshold: 50, occurrence_threshold_max: null, window_minutes: 10,
      severity: 'P1', priority: 10, is_active: true, description: null,
      updated_by: null, updated_at: null },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('IncidentPolicyConfig', () => {
  it('shows loading skeleton while fetching SLA policy', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<IncidentPolicyConfig />, { wrapper })
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state with retry on SLA load failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load SLA policy.')).toBeInTheDocument())
  })

  it('shows empty state when no SLA policies exist', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('No SLA policy rows found.')).toBeInTheDocument())
  })

  it('renders SLA policy rows on the default tab', async () => {
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())
    expect(screen.getByText('30 min SLA')).toBeInTheDocument()
    expect(screen.getByText('P1')).toBeInTheDocument()
  })

  it('edits an SLA policy row and saves', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    mockPatch.mockResolvedValue({ data: { message: 'SLA_POLICY_UPDATED', sla_policy: {} } })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())

    await user.click(screen.getAllByRole('button', { name: /^edit$/i })[0])
    const minutesInput = screen.getByLabelText(/sla \(minutes\)/i)
    await user.clear(minutesInput)
    await user.type(minutesInput, '45')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/sla-policy/P0', {
      sla_minutes: 45, auto_create_incident: true, description: 'Critical',
    }))
  })

  it('switches to the Classification Rules tab and loads rules', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())

    mockGet.mockResolvedValue({ data: RULES_MOCK })
    await user.click(screen.getByRole('button', { name: /classification rules/i }))

    await waitFor(() => expect(screen.getByText('BULK_DOC_ACCESS')).toBeInTheDocument())
    expect(mockGet).toHaveBeenLastCalledWith('/admin/severity-rules')
  })

  it('filters rules by domain', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())

    mockGet.mockResolvedValue({ data: RULES_MOCK })
    await user.click(screen.getByRole('button', { name: /classification rules/i }))
    await waitFor(() => expect(screen.getByText('BULK_DOC_ACCESS')).toBeInTheDocument())

    const domainSelect = screen.getByDisplayValue('All domains')
    await user.selectOptions(domainSelect, 'ANOMALY_RULE')
    await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith('/admin/severity-rules?domain=ANOMALY_RULE'))
  })

  it('edits a classification rule and saves', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())

    mockGet.mockResolvedValue({ data: RULES_MOCK })
    await user.click(screen.getByRole('button', { name: /classification rules/i }))
    await waitFor(() => expect(screen.getByText('BULK_DOC_ACCESS')).toBeInTheDocument())

    mockPatch.mockResolvedValue({ data: { message: 'SEVERITY_RULE_UPDATED', severity_rule: {} } })
    await user.click(screen.getByRole('button', { name: /^edit$/i }))
    const thresholdInput = screen.getByLabelText(/occurrence min/i)
    await user.clear(thresholdInput)
    await user.type(thresholdInput, '75')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/severity-rules/r-1', {
      occurrence_threshold: 75, occurrence_threshold_max: null, window_minutes: 10,
      severity: 'P1', priority: 10, is_active: true, description: null,
    }))
  })

  it('creates a new classification rule', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: SLA_MOCK })
    render(<IncidentPolicyConfig />, { wrapper })
    await waitFor(() => expect(screen.getByText('P0')).toBeInTheDocument())

    mockGet.mockResolvedValue({ data: { items: [] } })
    await user.click(screen.getByRole('button', { name: /classification rules/i }))
    await waitFor(() => expect(screen.getByText('No classification rules match this filter.')).toBeInTheDocument())

    mockPost.mockResolvedValue({ data: { message: 'SEVERITY_RULE_CREATED', severity_rule: {} } })
    await user.click(screen.getByRole('button', { name: /new rule/i }))
    const matchValueInput = screen.getByLabelText(/match value/i)
    await user.type(matchValueInput, 'NEW_RULE')
    await user.click(screen.getByRole('button', { name: /create rule/i }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/severity-rules', expect.objectContaining({
      domain: 'ANOMALY_RULE', match_type: 'EXACT', match_value: 'NEW_RULE', severity: 'P2', priority: 100,
    })))
  })
})
