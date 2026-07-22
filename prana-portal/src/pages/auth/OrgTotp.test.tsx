import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { OrgTotp } from './OrgTotp'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,x') } }))

const mockNavigate = vi.fn()
let searchParamsValue = ''
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual as any,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [new URLSearchParams(searchParamsValue)],
  }
})

// A fake JWT with a base64url-encoded payload — decodeJwtUser reads {sub, role, tenant_id}.
function fakeJwt(payload: object) {
  const b64 = btoa(JSON.stringify(payload))
  return `header.${b64}.sig`
}

beforeEach(() => {
  vi.clearAllMocks()
  searchParamsValue = ''
  useAuthStore.setState({ user: null, accessToken: null, stepToken: 'step-1', requiresTotpSetup: false })
})

function renderPage() {
  return render(<MemoryRouter><OrgTotp /></MemoryRouter>)
}

describe('OrgTotp — guard', () => {
  it('redirects to /org/login when there is no step token', () => {
    useAuthStore.setState({ stepToken: null })
    renderPage()
    expect(mockNavigate).toHaveBeenCalledWith('/org/login')
  })
})

describe('OrgTotp — verify (no setup)', () => {
  it('renders the 6-digit code input', () => {
    renderPage()
    expect(screen.getByPlaceholderText('000 000')).toBeInTheDocument()
  })

  it('on success: stores the access token + decoded user, clears stepToken, navigates to dashboard', async () => {
    const token = fakeJwt({ sub: 'u-1', role: 'oa_admin', tenant_id: 't-1' })
    vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: token } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('000 000'), '123456')
    await user.click(screen.getByRole('button', { name: /verify/i }))

    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe(token))
    expect(useAuthStore.getState().user?.userId).toBe('u-1')
    expect(useAuthStore.getState().user?.role).toBe('oa_admin')
    expect(useAuthStore.getState().stepToken).toBeNull()
    expect(mockNavigate).toHaveBeenCalledWith('/org/dashboard')
  })

  it('shows the lockout screen on ACCOUNT_LOCKED', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'ACCOUNT_LOCKED' } } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('000 000'), '000000')
    await user.click(screen.getByRole('button', { name: /verify/i }))

    expect(await screen.findByText('Account temporarily locked')).toBeInTheDocument()
  })

  it('shows a remaining-attempts warning as failures approach the lockout threshold', async () => {
    vi.mocked(api.post).mockRejectedValue({ response: { data: { detail: 'INVALID_TOTP' } } })
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByPlaceholderText('000 000')
    // LOCK_THRESHOLD is 5 — fail 3 times to get into the "2 attempts remaining" window
    for (let i = 0; i < 3; i++) {
      await user.clear(input)
      await user.type(input, '000000')
      await user.click(screen.getByRole('button', { name: /verify/i }))
      await screen.findByText(i < 2 ? /incorrect|invalid/i : /remaining/i)
    }
    expect(screen.getByText(/2 attempts remaining/i)).toBeInTheDocument()
  })

  it('shows a session-expired message for STEP_TOKEN_EXPIRED', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'STEP_TOKEN_EXPIRED' } } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('000 000'), '000000')
    await user.click(screen.getByRole('button', { name: /verify/i }))

    expect(await screen.findByText(/session/i)).toBeInTheDocument()
  })
})

describe('OrgTotp — first-login setup flow', () => {
  beforeEach(() => {
    searchParamsValue = 'setup=1'
  })

  it('shows the install-app step first', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /show qr/i })).toBeInTheDocument()
  })

  it('loads the QR code and backup codes, then advances to verify on confirmation', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { provisioning_uri: 'otpauth://totp/x', backup_codes: ['AAA-111', 'BBB-222'], setup_token: 'setup-tok' },
    })
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /show qr/i }))

    expect(await screen.findByAltText('TOTP QR code')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /scanned it/i }))
    expect(screen.getByPlaceholderText('000 000')).toBeInTheDocument()
  })

  it('confirms setup via the setup-confirm endpoint and activates the account', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { provisioning_uri: 'otpauth://totp/x', backup_codes: [], setup_token: 'setup-tok' },
    })
    const token = fakeJwt({ sub: 'u-2', role: 'oa_operator', tenant_id: 't-1' })
    vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: token } })

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /show qr/i }))
    await screen.findByAltText('TOTP QR code')
    await user.click(screen.getByRole('button', { name: /scanned it/i }))
    await user.type(screen.getByPlaceholderText('000 000'), '123456')
    await user.click(screen.getByRole('button', { name: /activate/i }))

    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe(token))
    expect(api.post).toHaveBeenCalledWith('/auth/org/totp-setup/confirm', { setup_token: 'setup-tok', code: '123456' })
    expect(useAuthStore.getState().requiresTotpSetup).toBe(false)
    expect(mockNavigate).toHaveBeenCalledWith('/org/dashboard')
  })
})
