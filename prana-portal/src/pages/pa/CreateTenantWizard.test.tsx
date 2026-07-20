import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CreateTenantWizard } from './CreateTenantWizard'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

beforeEach(() => vi.clearAllMocks())

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><CreateTenantWizard /></MemoryRouter></QueryClientProvider>)
}

describe('CreateTenantWizard — step 0 (Legal Identity)', () => {
  it('blocks advancing without required fields and shows validation errors', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('Organisation legal name is required')).toBeInTheDocument()
    expect(screen.getByText('Entity type is required')).toBeInTheDocument()
  })

  it('advances to step 1 once legal name and entity type are filled', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('e.g. TechCorp Solutions Private Limited'), 'Acme Pvt Ltd')
    await user.selectOptions(screen.getByText('Select entity type').closest('select')!, 'PRIVATE_LIMITED')
    await user.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('Registered Office Address')).toBeInTheDocument()
  })
})

async function goToStep1(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText('e.g. TechCorp Solutions Private Limited'), 'Acme Pvt Ltd')
  await user.selectOptions(screen.getByText('Select entity type').closest('select')!, 'PRIVATE_LIMITED')
  await user.click(screen.getByRole('button', { name: /^next$/i }))
  await screen.findByText('Registered Office Address')
}

describe('CreateTenantWizard — step 1 (Address & Contacts)', () => {
  it('blocks advancing without required address/contact fields', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToStep1(user)
    await user.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('Registered address Line 1 is required')).toBeInTheDocument()
  })
})

describe('CreateTenantWizard — step navigation (Back button)', () => {
  it('returns to step 0 when Back is clicked', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToStep1(user)
    await user.click(screen.getByRole('button', { name: /^back$/i }))
    expect(await screen.findByPlaceholderText('e.g. TechCorp Solutions Private Limited')).toBeInTheDocument()
  })

  it('disables the Back button on the first step', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /^back$/i })).toBeDisabled()
  })
})

describe('CreateTenantWizard — final submission', () => {
  // These 2 tests drive ~15 sequential interactions across all 5 wizard steps —
  // the heaviest tests in the suite. Under full-suite concurrent load (many jsdom
  // environments running at once), the default 1000ms findBy/waitFor timeout and
  // 5000ms test timeout can be exceeded by CPU contention alone even though the
  // component behaves correctly (confirmed: 100% reliable when run in isolation).
  // Give them explicit headroom rather than letting them flake under load.
  it('walks through all 5 steps and shows a failure message when tenant creation fails', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('conflict'))
    renderPage()

    // Step 0 — Legal Identity
    await user.type(screen.getByPlaceholderText('e.g. TechCorp Solutions Private Limited'), 'Acme Pvt Ltd')
    await user.selectOptions(screen.getByText('Select entity type').closest('select')!, 'PRIVATE_LIMITED')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    // Step 1 — Address & Contacts
    await screen.findByText('Registered Office Address')
    await user.type(screen.getByPlaceholderText('Building / Flat No., Street'), '123 MG Road')
    await user.type(screen.getByPlaceholderText('Mumbai'), 'Mumbai')
    await user.selectOptions(screen.getAllByText('Select state')[0].closest('select')!, 'Maharashtra')
    await user.type(screen.getByPlaceholderText('400001'), '400001')
    await user.type(screen.getByPlaceholderText('Priya Sharma'), 'Priya Sharma')
    await user.type(screen.getByPlaceholderText('CHRO / HR Head / IT Head'), 'HR Head')
    await user.type(screen.getByPlaceholderText('priya@company.in'), 'priya@acme.in')
    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '+919876543210')
    await user.type(screen.getByPlaceholderText('admin@company.in'), 'admin@acme.in')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    // Step 2 — Data Protection (DPDP)
    await screen.findByText('Data Protection & DPDP Compliance')
    const nameInputs = screen.getAllByPlaceholderText('Full name')
    await user.type(nameInputs[0], 'Deepa Rao')
    await user.type(screen.getByPlaceholderText('dpo@company.in'), 'dpo@acme.in')
    await user.type(nameInputs[1], 'Grievance Officer')
    await user.type(screen.getByPlaceholderText('grievance@company.in'), 'grievance@acme.in')
    await user.click(screen.getByText('Data Processing Agreement (DPA) v1.0'))
    await user.click(screen.getByText('Purpose Limitation Declaration'))
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    // Step 3 — Technical Configuration
    await screen.findByText('Corporate Domain')
    await user.type(screen.getByPlaceholderText('company.in'), 'acme.in')
    await user.selectOptions(screen.getAllByText('Select state')[0].closest('select')!, 'Maharashtra')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    // Step 4 — Workforce & Contract
    await screen.findByText('Review Summary')
    await user.selectOptions(screen.getByText('Select band').closest('select')!, '201-500')
    await user.click(screen.getByRole('button', { name: /create tenant/i }))

    await waitFor(() => expect(mockPost).toHaveBeenCalled(), { timeout: 5000 })
    expect(await screen.findByText('Failed to create tenant. Check all fields and try again.', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  }, 20000)

  it('navigates to /admin/tenants on successful creation', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { tenant_id: 't-new' } })
    renderPage()

    await user.type(screen.getByPlaceholderText('e.g. TechCorp Solutions Private Limited'), 'Acme Pvt Ltd')
    await user.selectOptions(screen.getByText('Select entity type').closest('select')!, 'PRIVATE_LIMITED')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('Registered Office Address')
    await user.type(screen.getByPlaceholderText('Building / Flat No., Street'), '123 MG Road')
    await user.type(screen.getByPlaceholderText('Mumbai'), 'Mumbai')
    await user.selectOptions(screen.getAllByText('Select state')[0].closest('select')!, 'Maharashtra')
    await user.type(screen.getByPlaceholderText('400001'), '400001')
    await user.type(screen.getByPlaceholderText('Priya Sharma'), 'Priya Sharma')
    await user.type(screen.getByPlaceholderText('CHRO / HR Head / IT Head'), 'HR Head')
    await user.type(screen.getByPlaceholderText('priya@company.in'), 'priya@acme.in')
    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '+919876543210')
    await user.type(screen.getByPlaceholderText('admin@company.in'), 'admin@acme.in')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('Data Protection & DPDP Compliance')
    const nameInputs = screen.getAllByPlaceholderText('Full name')
    await user.type(nameInputs[0], 'Deepa Rao')
    await user.type(screen.getByPlaceholderText('dpo@company.in'), 'dpo@acme.in')
    await user.type(nameInputs[1], 'Grievance Officer')
    await user.type(screen.getByPlaceholderText('grievance@company.in'), 'grievance@acme.in')
    await user.click(screen.getByText('Data Processing Agreement (DPA) v1.0'))
    await user.click(screen.getByText('Purpose Limitation Declaration'))
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('Corporate Domain')
    await user.type(screen.getByPlaceholderText('company.in'), 'acme.in')
    await user.selectOptions(screen.getAllByText('Select state')[0].closest('select')!, 'Maharashtra')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('Review Summary')
    await user.selectOptions(screen.getByText('Select band').closest('select')!, '201-500')
    await user.click(screen.getByRole('button', { name: /create tenant/i }))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/admin/tenants'), { timeout: 5000 })
  }, 20000)
})
