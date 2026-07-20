import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AdminLogin } from './AdminLogin'
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
  return render(<MemoryRouter><AdminLogin /></MemoryRouter>)
}

describe('AdminLogin', () => {
  it('renders the admin email and password fields', () => {
    renderPage()
    expect(screen.getByPlaceholderText('you@prana.in')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /continue to totp/i })).toBeInTheDocument()
  })

  it('on success, stores the step token and always navigates to /admin/totp', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'pa-step-1', requires_totp_setup: false } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@prana.in'), 'pa@prana.in')
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByRole('button', { name: /continue to totp/i }))

    await waitFor(() => expect(useAuthStore.getState().stepToken).toBe('pa-step-1'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/totp')
  })

  it('sets requiresTotpSetup on first login', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'pa-step-1', requires_totp_setup: true } })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@prana.in'), 'pa@prana.in')
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByRole('button', { name: /continue to totp/i }))

    await waitFor(() => expect(useAuthStore.getState().requiresTotpSetup).toBe(true))
  })

  it('shows a PA-specific fallback error message on failure with no detail', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('down'))
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('you@prana.in'), 'pa@prana.in')
    await user.type(document.querySelector('input[type="password"]')!, 'wrong')
    await user.click(screen.getByRole('button', { name: /continue to totp/i }))

    expect(await screen.findByText('Login failed. Verify your @prana.in credentials.')).toBeInTheDocument()
  })

  it('navigates back to org login', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText('Sign in here'))
    expect(mockNavigate).toHaveBeenCalledWith('/org/login')
  })
})
