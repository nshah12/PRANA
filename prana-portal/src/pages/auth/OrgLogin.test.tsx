import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { OrgLogin } from './OrgLogin'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual as any, useNavigate: () => mockNavigate }
})

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false })
})

function renderPage() {
  return render(<MemoryRouter><OrgLogin /></MemoryRouter>)
}

describe('OrgLogin', () => {
  it('renders the email and password fields', () => {
    renderPage()
    expect(screen.getByPlaceholderText('you@company.in')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /continue to 2fa/i })).toBeInTheDocument()
  })

  it('on success, stores the step token and navigates to /org/totp when no reset/setup is required', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { step_token: 'step-abc', requires_totp_setup: false, requires_password_reset: false },
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@company.in'), 'oa@acme.example')
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByRole('button', { name: /continue to 2fa/i }))

    await waitFor(() => expect(useAuthStore.getState().stepToken).toBe('step-abc'))
    expect(mockNavigate).toHaveBeenCalledWith('/org/totp?setup=0')
  })

  it('routes to /org/reset when the API says a password reset is required', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { step_token: 'step-abc', requires_totp_setup: false, requires_password_reset: true },
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@company.in'), 'oa@acme.example')
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByRole('button', { name: /continue to 2fa/i }))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/org/reset'))
  })

  it('marks requiresTotpSetup and routes with setup=1 on first login', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { step_token: 'step-abc', requires_totp_setup: true, requires_password_reset: false },
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@company.in'), 'oa@acme.example')
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByRole('button', { name: /continue to 2fa/i }))

    await waitFor(() => expect(useAuthStore.getState().requiresTotpSetup).toBe(true))
    expect(mockNavigate).toHaveBeenCalledWith('/org/totp?setup=1')
  })

  it('shows the API error detail on failed login', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'Incorrect email or password.' } } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@company.in'), 'oa@acme.example')
    await user.type(document.querySelector('input[type="password"]')!, 'wrong')
    await user.click(screen.getByRole('button', { name: /continue to 2fa/i }))

    expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument()
  })

  it('falls back to a generic message when the error has no detail', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('network down'))
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@company.in'), 'oa@acme.example')
    await user.type(document.querySelector('input[type="password"]')!, 'wrong')
    await user.click(screen.getByRole('button', { name: /continue to 2fa/i }))

    expect(await screen.findByText('Login failed. Check your credentials.')).toBeInTheDocument()
  })

  it('opens the forgot-password modal and closes it again', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText(/forgot/i))
    expect(screen.getByText(/User Management/)).toBeInTheDocument()
    await user.click(screen.getByText('Got it'))
    expect(screen.queryByText(/User Management/)).not.toBeInTheDocument()
  })

  it('navigates to the admin login when the PA link is clicked', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText('Sign in here'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/login')
  })
})
