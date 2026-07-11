/**
 * OrgProfile tests
 *
 *  1. Loading state
 *  2. Renders read-only Legal Identity fields from API (open by default)
 *  3. Editable brand name field is pre-filled and editable
 *  4. Collapsible sections expand/collapse (Addresses section starts closed)
 *  5. Save changes calls PATCH with only populated fields, shows "Saved" then reverts
 *  6. Nested address fields update independently (reg vs corp)
 *  7. DPA acceptance banner shown when dpa_accepted_at present
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { OrgProfile } from './OrgProfile'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = {
  tenant_name: 'Acme Technologies Pvt Ltd',
  brand_name: 'Acme',
  cin: 'U72900MH2015PTC123456',
  gstin: '27ABCDE1234F1Z5',
  entity_type: 'Private Limited',
  incorporation_date: '2015-04-01',
  roc_jurisdiction: 'ROC Mumbai',
  pan_entity: 'ABCDE1234F',
  tan: 'MUMB12345A',
  status: 'ACTIVE',
  home_region: 'ap-south-1',
  domain: 'acme.in',
  reg_address: { line1: 'Tower A', city: 'Mumbai', state: 'Maharashtra', pincode: '400001' },
  corp_address: {},
  primary_contact: { name: 'Priya Sharma', designation: 'CHRO', email: 'priya@acme.in', mobile: '+91 98765 43210' },
  dpo_name: 'Rakesh Gupta',
  dpo_email: 'dpo@acme.in',
}

beforeEach(() => vi.clearAllMocks())

describe('OrgProfile', () => {
  it('shows loading state while fetching profile', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<OrgProfile />, { wrapper })
    expect(screen.getByText('Loading profile…')).toBeInTheDocument()
  })

  it('renders read-only Legal Identity fields (section open by default)', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<OrgProfile />, { wrapper })
    expect(await screen.findByText('Acme Technologies Pvt Ltd')).toBeInTheDocument()
    expect(screen.getByText('U72900MH2015PTC123456')).toBeInTheDocument()
    expect(screen.getByText('27ABCDE1234F1Z5')).toBeInTheDocument()
    expect(screen.getByText('ABCDE1234F')).toBeInTheDocument()
  })

  it('pre-fills the editable brand name field', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<OrgProfile />, { wrapper })
    await screen.findByText('Acme Technologies Pvt Ltd')
    const brandInput = screen.getByPlaceholderText('Common operating name') as HTMLInputElement
    expect(brandInput.value).toBe('Acme')
  })

  it('Addresses section is collapsed by default and expands on click', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<OrgProfile />, { wrapper })
    await screen.findByText('Acme Technologies Pvt Ltd')

    expect(screen.queryByText('Registered Office Address')).not.toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByText('Addresses'))
    expect(await screen.findByText('Registered Office Address')).toBeInTheDocument()
  })

  it('saves changes with PATCH containing populated fields, then shows Saved confirmation', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    mockPatch.mockResolvedValue({ data: {} })
    render(<OrgProfile />, { wrapper })
    await screen.findByText('Acme Technologies Pvt Ltd')

    const user = userEvent.setup()
    const brandInput = screen.getByPlaceholderText('Common operating name')
    await user.clear(brandInput)
    await user.type(brandInput, 'Acme Corp')

    await user.click(screen.getByRole('button', { name: /Save changes/ }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/v1/org/profile', expect.objectContaining({
      brand_name: 'Acme Corp',
    })))
    expect((await screen.findAllByText('Saved')).length).toBeGreaterThan(0)
  })

  it('updates registered and corporate addresses independently', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<OrgProfile />, { wrapper })
    await screen.findByText('Acme Technologies Pvt Ltd')

    const user = userEvent.setup()
    await user.click(screen.getByText('Addresses'))
    await screen.findByText('Registered Office Address')

    const cityInputs = screen.getAllByPlaceholderText('Mumbai')
    expect((cityInputs[0] as HTMLInputElement).value).toBe('Mumbai')

    const corpCityInput = screen.getByPlaceholderText('Bangalore') as HTMLInputElement
    await user.type(corpCityInput, 'Bengaluru')
    expect(corpCityInput.value).toBe('Bengaluru')
    // reg_address city is untouched
    expect((screen.getAllByPlaceholderText('Mumbai')[0] as HTMLInputElement).value).toBe('Mumbai')
  })

  it('shows DPA acceptance banner when dpa_accepted_at is present', async () => {
    mockGet.mockResolvedValue({ data: { ...PROFILE, dpa_accepted_at: '2024-01-15T00:00:00Z', dpa_version: '2.1' } })
    render(<OrgProfile />, { wrapper })
    await screen.findByText('Acme Technologies Pvt Ltd')

    const user = userEvent.setup()
    await user.click(screen.getByText('Data Protection Officers (DPDP Act 2023)'))

    expect(await screen.findByText(/DPA v2.1 accepted on/)).toBeInTheDocument()
  })
})
