import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ResetPassword } from './ResetPassword'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual as any, useNavigate: () => mockNavigate }
})

const STRONG_PASSWORD = 'Sup3r$ecretPass'

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: null, accessToken: null, stepToken: 'reset-step-token', requiresTotpSetup: false })
})

function renderPage() {
  return render(<MemoryRouter><ResetPassword /></MemoryRouter>)
}

function inputs() {
  const [pwd, confirm] = screen.getAllByPlaceholderText(/./).filter(el =>
    el.tagName === 'INPUT' && (el as HTMLInputElement).type === 'password',
  )
  return { pwd, confirm }
}

describe('ResetPassword', () => {
  it('disables submit until all password strength rules pass', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /set password/i })).toBeDisabled()
  })

  it('shows a mismatch error and does not call the API when passwords differ', async () => {
    const user = userEvent.setup()
    renderPage()
    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, 'Different1234$')
    // Button is only enabled once allRulesPassed is true for the first field —
    // the mismatch check happens inside onSubmit.
    await user.click(screen.getByRole('button', { name: /set password/i }))

    expect(await screen.findByText(/do not match|mismatch/i)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('on success: updates the step token and navigates to /org/totp', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'totp-step-2' } })
    const user = userEvent.setup()
    renderPage()
    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, STRONG_PASSWORD)
    await user.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => expect(useAuthStore.getState().stepToken).toBe('totp-step-2'))
    expect(mockNavigate).toHaveBeenCalledWith('/org/totp')
    expect(api.post).toHaveBeenCalledWith('/auth/org/password-reset', {
      step_token: 'reset-step-token',
      new_password: STRONG_PASSWORD,
    })
  })

  it('shows a session-expired message for STEP_TOKEN_EXPIRED', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'STEP_TOKEN_EXPIRED' } } })
    const user = userEvent.setup()
    renderPage()
    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, STRONG_PASSWORD)
    await user.click(screen.getByRole('button', { name: /set password/i }))

    expect(await screen.findByText(/session/i)).toBeInTheDocument()
  })
})
