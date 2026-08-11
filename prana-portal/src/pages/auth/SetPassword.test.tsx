import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { SetPassword } from './SetPassword'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
let mockSearchParams = new URLSearchParams('token=real-setup-token')
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual as any,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [mockSearchParams],
  }
})

const STRONG_PASSWORD = 'Sup3r$ecretPass'

beforeEach(() => {
  vi.clearAllMocks()
  mockSearchParams = new URLSearchParams('token=real-setup-token')
})

function renderPage() {
  return render(<MemoryRouter><SetPassword /></MemoryRouter>)
}

function inputs() {
  const [pwd, confirm] = screen.getAllByPlaceholderText(/./).filter(el =>
    el.tagName === 'INPUT' && (el as HTMLInputElement).type === 'password',
  )
  return { pwd, confirm }
}

describe('SetPassword', () => {
  it('shows a checking state, then verifies the token and shows the form with the account email', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { valid: true, email: 'chro@acme.com' } })
    renderPage()

    expect(screen.getByText(/checking/i)).toBeInTheDocument()
    expect(await screen.findByText(/chro@acme\.com/)).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/auth/org/password-setup/verify', { token: 'real-setup-token' })
  })

  it('shows an invalid-link message when no token is present in the URL', async () => {
    mockSearchParams = new URLSearchParams('')
    renderPage()
    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows an invalid-link message when verification fails (expired/used token)', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'SETUP_TOKEN_EXPIRED' } } })
    renderPage()
    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument()
  })

  it('disables submit until all password strength rules pass', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { valid: true, email: 'chro@acme.com' } })
    renderPage()
    await screen.findByText(/chro@acme\.com/)
    expect(screen.getByRole('button', { name: /set password/i })).toBeDisabled()
  })

  it('shows a mismatch error and does not call the setup API when passwords differ', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { valid: true, email: 'chro@acme.com' } })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(/chro@acme\.com/)

    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, 'Different1234$')
    await user.click(screen.getByRole('button', { name: /set password/i }))

    expect(await screen.findByText(/do not match|mismatch/i)).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledTimes(1)   // only the verify call, never setup
  })

  it('on success: calls password-setup with the URL token and shows the done state', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { valid: true, email: 'chro@acme.com' } })   // verify
      .mockResolvedValueOnce({ data: { message: 'PASSWORD_CHANGED' } })            // setup

    const user = userEvent.setup()
    renderPage()
    await screen.findByText(/chro@acme\.com/)

    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, STRONG_PASSWORD)
    await user.click(screen.getByRole('button', { name: /set password/i }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/org/password-setup', {
      token: 'real-setup-token',
      new_password: STRONG_PASSWORD,
    }))
    expect(await screen.findByText(/password set/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /go to login/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/org/login')
  })

  it('falls back to the invalid-link state if the token expires between verify and submit', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { valid: true, email: 'chro@acme.com' } })
      .mockRejectedValueOnce({ response: { data: { detail: 'SETUP_TOKEN_EXPIRED' } } })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText(/chro@acme\.com/)

    const { pwd, confirm } = inputs()
    await user.type(pwd, STRONG_PASSWORD)
    await user.type(confirm, STRONG_PASSWORD)
    await user.click(screen.getByRole('button', { name: /set password/i }))

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument()
  })
})
