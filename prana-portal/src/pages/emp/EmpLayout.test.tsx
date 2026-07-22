import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { EmpLayout } from './EmpLayout'
import { useEmpAuthStore } from '@/store/empAuth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

beforeEach(() => {
  vi.clearAllMocks()
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
})

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/emp/vault']}>
      <Routes>
        <Route path="/emp" element={<EmpLayout />}>
          <Route path="vault" element={<div>Vault Page Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('EmpLayout', () => {
  it('renders the nav items and page outlet content', () => {
    renderLayout()
    expect(screen.getByText('My Vault')).toBeInTheDocument()
    expect(screen.getByText('Vault Health')).toBeInTheDocument()
    expect(screen.getByText('Shared Documents')).toBeInTheDocument()
    expect(screen.getByText('Privacy Cockpit')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
    expect(screen.getByText('Vault Page Content')).toBeInTheDocument()
  })

  it('shows the default employee name when no user is set', () => {
    renderLayout()
    expect(screen.getByText('Employee')).toBeInTheDocument()
  })

  it("shows the user's name and mobile when logged in", () => {
    useEmpAuthStore.setState({
      user: { userId: 'u1', name: 'Rahul Sharma', email: '', mobile: '+919000000001', pan_token: '', vault_url: '' },
      accessToken: 'tok', stepToken: null,
    })
    renderLayout()
    expect(screen.getByText('Rahul Sharma')).toBeInTheDocument()
    expect(screen.getByText('+919000000001')).toBeInTheDocument()
  })

  it('signs out: calls logout endpoint, clears store, and navigates to /emp/login', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: {} })
    useEmpAuthStore.setState({
      user: { userId: 'u1', name: 'Rahul Sharma', email: '', mobile: '', pan_token: '', vault_url: '' },
      accessToken: 'tok', stepToken: null,
    })
    const user = userEvent.setup()
    renderLayout()

    await user.click(screen.getByText('Sign out'))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/employee/logout'))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/emp/login'))
    expect(useEmpAuthStore.getState().user).toBeNull()
    expect(useEmpAuthStore.getState().accessToken).toBeNull()
  })

  it('signs out even when the logout API call fails', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('network'))
    const user = userEvent.setup()
    renderLayout()

    await user.click(screen.getByText('Sign out'))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/emp/login'))
  })

  it('toggles the mobile drawer open and closed', async () => {
    const user = userEvent.setup()
    renderLayout()
    const openBtn = screen.getByLabelText('Open navigation')
    await user.click(openBtn)
    expect(screen.getByLabelText('Close navigation')).toBeInTheDocument()
    await user.click(screen.getByLabelText('Close navigation'))
    expect(screen.getByLabelText('Open navigation')).toBeInTheDocument()
  })
})
