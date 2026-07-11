import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { EmpLogin } from './EmpLogin'
import { useEmpAuthStore } from '@/store/empAuth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() }, getApiBase: () => '/api' }))
import { api } from '@/lib/api'
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,x') } }))

function fakeJwt(payload: object) {
  const b64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_')
  return `header.${b64}.sig`
}

function setLocation() {
  const original = window.location
  // @ts-expect-error test override
  delete window.location
  // @ts-expect-error partial stub — only href is read/written by finishLogin
  window.location = { href: '' }
  return () => {
    // @ts-expect-error restore
    delete window.location
    // @ts-expect-error restore — original was captured before the delete/stub above
    window.location = original
  }
}

let restoreLocation: () => void

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
  restoreLocation = setLocation()
})

afterEach(() => {
  restoreLocation()
})

function renderPage() {
  return render(<MemoryRouter><EmpLogin /></MemoryRouter>)
}

describe('EmpLogin — identifier step', () => {
  it('requires an identifier before advancing', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText(/continue/i))
    await waitFor(() => expect(document.querySelector('.text-red-400')).not.toBeNull())
    expect(document.querySelector('.text-red-400')?.textContent).toMatch(/enter your email/i)
  })

  it('advances to the password step once an identifier is entered', async () => {
    const user = userEvent.setup()
    renderPage()
    const inputs = screen.getAllByRole('textbox')
    await user.type(inputs[0], 'rahul@example.com')
    await user.click(screen.getByText(/continue/i))
    expect(await screen.findByPlaceholderText(/password/i)).toBeInTheDocument()
  })
})

async function goToPasswordStep(user: ReturnType<typeof userEvent.setup>) {
  const inputs = screen.getAllByRole('textbox')
  await user.type(inputs[0], 'rahul@example.com')
  await user.click(screen.getByText(/continue/i))
  await screen.findByPlaceholderText(/password/i)
}

describe('EmpLogin — password step', () => {
  it('routes to the totp step when next="totp"', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'totp' } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByText(/continue/i))

    expect(await screen.findByPlaceholderText(/6-digit|code/i)).toBeInTheDocument()
    expect(useEmpAuthStore.getState().stepToken).toBe('step-1')
  })

  it('routes to force_password when next="force_password"', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'force_password' } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'temp-pass')
    await user.click(screen.getByText(/continue/i))

    expect(await screen.findByPlaceholderText('New password (min 8 chars)')).toBeInTheDocument()
  })

  it('routes to consent when next="consent"', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'consent' } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByText(/continue/i))

    expect(await screen.findByRole('button', { name: /accept/i })).toBeInTheDocument()
  })

  it('routes to totp_setup and loads a QR code when next="totp_setup"', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'totp_setup' } })
      .mockResolvedValueOnce({ data: { provisioning_uri: 'otpauth://totp/x' } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByText(/continue/i))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/employee/setup/totp/init', { step_token: 'step-1' }))
    expect(await screen.findByAltText(/qr/i)).toBeInTheDocument()
  })

  it.each([
    ['INVALID_CREDENTIALS', /incorrect password or account not found/i],
    ['ACCOUNT_LOCKED', /locked/i],
    ['ACCOUNT_NOT_ACTIVE', /not activated/i],
  ])('shows the mapped error for %s', async (detail, expected) => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail } } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'wrong')
    await user.click(screen.getByText(/continue/i))

    expect(await screen.findByText(expected)).toBeInTheDocument()
  })
})

describe('EmpLogin — TOTP step', () => {
  async function goToTotpStep(user: ReturnType<typeof userEvent.setup>) {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'totp' } })
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByText(/continue/i))
    await screen.findByPlaceholderText(/6-digit|code/i)
  }

  it('on success: persists the user (not the token) and navigates to /emp/vault', async () => {
    const token = fakeJwt({ sub: 'eu-1' })
    const user = userEvent.setup()
    renderPage()
    await goToTotpStep(user)
    vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: token } })

    await user.type(screen.getByPlaceholderText(/6-digit|code/i), '123456')
    await user.click(screen.getByText(/sign in to vault/i))

    await waitFor(() => expect(window.location.href).toBe('/emp/vault'))
    // Access token is held in memory only — never persisted to localStorage (security).
    expect(useEmpAuthStore.getState().accessToken).toBe(token)
    const stored = JSON.parse(localStorage.getItem('prana-emp-auth') as string)
    expect(stored.state.accessToken).toBeUndefined()
    expect(stored.state.user.userId).toBe('eu-1')
  })

  it('shows an invalid-code error on INVALID_TOTP', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToTotpStep(user)
    vi.mocked(api.post).mockRejectedValueOnce({ response: { data: { detail: 'INVALID_TOTP' } } })

    await user.type(screen.getByPlaceholderText(/6-digit|code/i), '000000')
    await user.click(screen.getByText(/sign in to vault/i))

    expect(await screen.findByText(/incorrect code/i)).toBeInTheDocument()
  })
})

describe('EmpLogin — force password step', () => {
  async function goToForcePasswordStep(user: ReturnType<typeof userEvent.setup>) {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'force_password' } })
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'temp-pass')
    await user.click(screen.getByText(/continue/i))
    await screen.findByPlaceholderText('New password (min 8 chars)')
  }

  it('rejects a too-short new password without calling the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToForcePasswordStep(user)
    await user.type(screen.getByPlaceholderText('New password (min 8 chars)'), 'short')
    await user.type(screen.getByPlaceholderText(/confirm/i), 'short')
    await user.click(screen.getByText(/set password/i))

    expect(await screen.findByText(/at least 8/i)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalledWith('/auth/employee/setup/password', expect.anything())
  })

  it('rejects mismatched passwords without calling the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToForcePasswordStep(user)
    await user.type(screen.getByPlaceholderText('New password (min 8 chars)'), 'longenoughpassword1')
    await user.type(screen.getByPlaceholderText(/confirm/i), 'longenoughpassword2')
    await user.click(screen.getByText(/set password/i))

    expect(await screen.findByText(/match/i)).toBeInTheDocument()
  })

  it('on success, advances via the returned next step', async () => {
    const user = userEvent.setup()
    renderPage()
    await goToForcePasswordStep(user)
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-2', next: 'consent' } })
    await user.type(screen.getByPlaceholderText('New password (min 8 chars)'), 'longenoughpassword1')
    await user.type(screen.getByPlaceholderText(/confirm/i), 'longenoughpassword1')
    await user.click(screen.getByText(/set password/i))

    expect(await screen.findByRole('button', { name: /accept/i })).toBeInTheDocument()
  })
})

describe('EmpLogin — consent step', () => {
  it('accepting consent finishes login and navigates to /emp/vault', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: { step_token: 'step-1', next: 'consent' } })
    const user = userEvent.setup()
    renderPage()
    await goToPasswordStep(user)
    await user.type(document.querySelector('input[type="password"]')!, 'secret123')
    await user.click(screen.getByText(/continue/i))
    await screen.findByRole('button', { name: /accept/i })

    const token = fakeJwt({ sub: 'eu-2' })
    vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: token } })
    await user.click(screen.getByRole('button', { name: /accept/i }))

    await waitFor(() => expect(window.location.href).toBe('/emp/vault'))
  })
})
