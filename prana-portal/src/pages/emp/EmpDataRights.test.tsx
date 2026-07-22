import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpDataRights } from './EmpDataRights'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue({ data: { consents: [] } })
})

async function openPanel(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByText(label))
}

describe('EmpDataRights', () => {
  it('renders the DPDP rights title, sub, and info banner', () => {
    render(<EmpDataRights />, { wrapper })
    expect(screen.getByText('DPDP Rights')).toBeInTheDocument()
    expect(screen.getByText("Your rights under India's Digital Personal Data Protection Act, 2023 — all exercisable from here")).toBeInTheDocument()
    expect(screen.getByText('These are your legally enforceable rights under the DPDP Act 2023. PRANA is the first platform to make all 6 rights fully exercisable from your phone.')).toBeInTheDocument()
  })

  it('lists all 5 exercisable DPDP right panels', () => {
    render(<EmpDataRights />, { wrapper })
    expect(screen.getByText('Right to Access')).toBeInTheDocument()
    expect(screen.getByText('Right to Correction')).toBeInTheDocument()
    expect(screen.getByText('Right to Erasure')).toBeInTheDocument()
    expect(screen.getByText('Right to Grievance Redressal')).toBeInTheDocument()
    expect(screen.getByText('Right to Nomination')).toBeInTheDocument()
    expect(screen.getByText('Right to Withdraw Consent')).toBeInTheDocument()
  })

  // ── Access (export) ──────────────────────────────────────────────
  it('Access panel: submits an export request and shows the SLA-bearing success message from copy', async () => {
    mockPost.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })

    await openPanel(user, 'Right to Access')
    await user.click(screen.getByRole('button', { name: 'Download My Data' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/dpdp/export'))
    expect(await screen.findByText('Export requested. We\'ll notify you when it\'s ready (typically within 2 hours).')).toBeInTheDocument()
  })

  // ── Correction ────────────────────────────────────────────────────
  it('Correction panel: requires field and correct value before submit', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Correction')

    await user.click(screen.getByRole('button', { name: 'Submit correction request' }))
    expect(await screen.findByText('Field and correct value required.')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('Correction panel: submits with correct payload and shows success', async () => {
    mockPost.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Correction')

    await user.type(screen.getByPlaceholderText('Field name (e.g. designation, department)'), 'designation')
    await user.type(screen.getByPlaceholderText('Current (incorrect) value'), 'Analyst')
    await user.type(screen.getByPlaceholderText('Correct value'), 'Senior Analyst')
    await user.click(screen.getByRole('button', { name: 'Submit correction request' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/dpdp/correction', {
      field: 'designation', current_value: 'Analyst', correct_value: 'Senior Analyst', evidence_note: '',
    }))
    expect(await screen.findByText('Correction request submitted. Our team reviews within 7 working days.')).toBeInTheDocument()
  })

  // ── Erasure ───────────────────────────────────────────────────────
  it('Erasure panel: shows the legal-retention warning and requires confirmation checkbox', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Erasure')

    expect(screen.getByText(/This will delete your account and all documents from PRANA\. Employer audit copies required by law may be retained for 7 years\./)).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: 'Request account erasure' })
    expect(btn).toBeDisabled()
  })

  it('Erasure panel: submits erasure request once confirmed', async () => {
    mockPost.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Erasure')

    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Request account erasure' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/dpdp/erasure', { reason: '' }))
    expect(await screen.findByText('Erasure request received. Processing begins within 30 days (DPDP Act 2023).')).toBeInTheDocument()
  })

  // ── Grievance ─────────────────────────────────────────────────────
  it('Grievance panel: requires subject and description before submit', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Grievance Redressal')

    await user.click(screen.getByRole('button', { name: 'Submit grievance' }))
    expect(await screen.findByText('Subject and description required.')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('Grievance panel: submits with correct payload and shows success', async () => {
    mockPost.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Grievance Redressal')

    await user.type(screen.getByPlaceholderText('Subject'), 'Wrong designation shown')
    await user.type(screen.getByPlaceholderText('Describe your grievance in detail…'), 'My designation is incorrect in the vault.')
    await user.click(screen.getByRole('button', { name: 'Submit grievance' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/dpdp/grievance', {
      subject: 'Wrong designation shown', description: 'My designation is incorrect in the vault.',
    }))
    expect(await screen.findByText('Grievance submitted. Our Grievance Officer will respond within 30 days.')).toBeInTheDocument()
  })

  // ── Nomination ────────────────────────────────────────────────────
  it('Nomination panel: Save Nominee is disabled until name and mobile provided', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Nomination')

    expect(screen.getByRole('button', { name: 'Save Nominee' })).toBeDisabled()
    await user.type(screen.getByPlaceholderText('Nominee full name'), 'Priya Sharma')
    await user.type(screen.getByPlaceholderText('Nominee mobile number'), '+919000000002')
    expect(screen.getByRole('button', { name: 'Save Nominee' })).toBeEnabled()
  })

  it('Nomination panel: shows success after saving', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Nomination')

    await user.type(screen.getByPlaceholderText('Nominee full name'), 'Priya Sharma')
    await user.type(screen.getByPlaceholderText('Nominee mobile number'), '+919000000002')
    await user.click(screen.getByRole('button', { name: 'Save Nominee' }))

    expect(await screen.findByText('Nominee saved. They can request vault access on your behalf.')).toBeInTheDocument()
  })

  // ── Consent ───────────────────────────────────────────────────────
  it('Consent panel: shows local toggle fallback when API returns no consents', async () => {
    mockGet.mockResolvedValue({ data: { consents: [] } })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Withdraw Consent')

    expect(await screen.findByText('Contribute anonymised data to org analytics')).toBeInTheDocument()
    expect(screen.getByText('Contribute to industry salary benchmarking')).toBeInTheDocument()
    expect(screen.getByText('Anomaly detection pattern contribution')).toBeInTheDocument()
  })

  it('Consent panel: renders real consent records with withdraw action', async () => {
    mockGet.mockResolvedValue({
      data: {
        consents: [
          { id: 'c1', purpose: 'analytics', purpose_label: 'Org analytics', consented_at: '2024-01-01T00:00:00Z', consent_version: '1', is_active: true },
        ],
      },
    })
    mockPost.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Withdraw Consent')

    expect(await screen.findByText('Org analytics')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Withdraw' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/dpdp/consents/c1/withdraw'))
  })

  it('Consent panel: shows the DPDP consent warning banner', async () => {
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    await openPanel(user, 'Right to Withdraw Consent')
    expect(await screen.findByText(/Withdrawing consent for document processing may prevent PRANA from delivering insights\. Your documents remain but won't be re-analysed\./)).toBeInTheDocument()
  })

  // ── Footer / legal links ──────────────────────────────────────────
  it('renders the DPDP compliance footer with privacy and grievance links', () => {
    render(<EmpDataRights />, { wrapper })
    expect(screen.getByText('Privacy Policy')).toBeInTheDocument()
    expect(screen.getByText('Grievance page')).toBeInTheDocument()
  })

  // ── Privacy contract ────────────────────────────────────────────
  it('never renders a raw rupee figure or PAN-shaped value anywhere on the DPDP rights page — privacy contract', async () => {
    mockGet.mockResolvedValue({
      data: {
        consents: [
          { id: 'c1', purpose: 'analytics', purpose_label: 'Org analytics', consented_at: '2024-01-01T00:00:00Z', consent_version: '1', is_active: true },
        ],
      },
    })
    const user = userEvent.setup()
    render(<EmpDataRights />, { wrapper })
    // Open every panel so all rendered content is captured
    for (const label of ['Right to Access', 'Right to Correction', 'Right to Erasure', 'Right to Grievance Redressal', 'Right to Nomination', 'Right to Withdraw Consent']) {
      await user.click(screen.getByText(label))
    }
    await screen.findByText('Org analytics')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
