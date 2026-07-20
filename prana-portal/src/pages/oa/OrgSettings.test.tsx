/**
 * OrgSettings tests
 *
 *  1. Renders default channel state (personal_email checked) before data loads
 *  2. Loads channels from API and reflects them as checked
 *  3. Toggling a channel enables Save; save is disabled until dirty
 *  4. Save calls PATCH with joined channel string, shows Saved confirmation
 *  5. Cannot uncheck the last remaining channel
 *  6. BFSI tenant: SMS channel is locked/disabled and shows "Disabled for BFSI"
 *  7. BFSI tenant with SMS pre-selected: shows blocking error and disables Save
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { OrgSettings } from './OrgSettings'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('OrgSettings', () => {
  it('renders the activation channels section with default personal_email checked before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<OrgSettings />, { wrapper })
    expect(screen.getByText('Employee Activation Channels')).toBeInTheDocument()
    expect(screen.getByText('Personal email')).toBeInTheDocument()
  })

  it('loads channels from the API and reflects them as checked', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'work_email,sms', self_upload_policy: 'ALLOWED' } })
    render(<OrgSettings />, { wrapper })

    // wait on the Save button becoming disabled again after the effect applies loaded
    // channels and resets dirty=false — a static label alone would resolve before data loads
    await waitFor(() => {
      const workLabel = screen.getByText('Work / corporate email').closest('label') as HTMLElement
      expect(workLabel.className).toMatch(/border-violet-500/)
    })
    const smsLabel = screen.getByText('SMS to registered mobile').closest('label') as HTMLElement
    expect(smsLabel.className).toMatch(/border-violet-500/)
    const personalLabel = screen.getByText('Personal email').closest('label') as HTMLElement
    expect(personalLabel.className).not.toMatch(/border-violet-500/)
  })

  it('toggling a channel marks the form dirty and enables Save', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'personal_email', self_upload_policy: 'ALLOWED' } })
    render(<OrgSettings />, { wrapper })
    await screen.findByText('Personal email')

    const saveBtn = screen.getByRole('button', { name: /Save settings/ })
    expect(saveBtn).toBeDisabled()

    const user = userEvent.setup()
    await user.click(screen.getByText('Work / corporate email'))
    expect(saveBtn).not.toBeDisabled()
  })

  it('saves the joined channel string and shows Saved confirmation', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'personal_email', self_upload_policy: 'ALLOWED' } })
    mockPatch.mockResolvedValue({ data: {} })
    render(<OrgSettings />, { wrapper })
    await screen.findByText('Personal email')

    const user = userEvent.setup()
    await user.click(screen.getByText('Work / corporate email'))
    await user.click(screen.getByRole('button', { name: /Save settings/ }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/v1/org/settings', {
      employee_activation_channels: 'personal_email,work_email',
    }))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('cannot uncheck the last remaining channel — it stays checked', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'personal_email', self_upload_policy: 'ALLOWED' } })
    render(<OrgSettings />, { wrapper })
    await screen.findByText('Personal email')

    const user = userEvent.setup()
    await user.click(screen.getByText('Personal email'))

    // the only channel remains checked even though the click was a no-op guard
    const label = screen.getByText('Personal email').closest('label') as HTMLElement
    expect(label.className).toMatch(/border-violet-500/)
  })

  it('BFSI tenant: SMS channel is locked and shows the disabled note', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'personal_email', self_upload_policy: 'BLOCKED_ENTIRELY' } })
    render(<OrgSettings />, { wrapper })

    expect(await screen.findByText('Disabled for BFSI')).toBeInTheDocument()
    const smsLabel = screen.getByText('SMS to registered mobile').closest('label') as HTMLElement
    expect(smsLabel.className).toContain('cursor-not-allowed')
  })

  it('BFSI tenant with SMS already selected shows blocking error and disables Save', async () => {
    mockGet.mockResolvedValue({ data: { employee_activation_channels: 'personal_email,sms', self_upload_policy: 'BLOCKED_ENTIRELY' } })
    render(<OrgSettings />, { wrapper })
    await screen.findByText('SMS to registered mobile')

    expect(await screen.findByText('SMS is not allowed for BFSI tenants. Remove it before saving.')).toBeInTheDocument()
    // dirty is false right after load, so button is disabled for that reason too;
    // toggle another channel to become dirty and confirm the BFSI+SMS error still blocks Save
    const user = userEvent.setup()
    await user.click(screen.getByText('Work / corporate email'))
    expect(screen.getByRole('button', { name: /Save settings/ })).toBeDisabled()
  })
})
