import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmployeePasswordReset } from './EmployeePasswordReset'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('EmployeePasswordReset (OA-Admin)', () => {
  it('renders the title and identifier input', () => {
    render(<EmployeePasswordReset />, { wrapper })
    expect(screen.getByRole('heading', { name: 'Reset Employee Password' })).toBeInTheDocument()
    expect(screen.getByLabelText('Employee email or mobile number')).toBeInTheDocument()
  })

  it('disables the submit button until an identifier is entered', async () => {
    const user = userEvent.setup()
    render(<EmployeePasswordReset />, { wrapper })
    const btn = screen.getByRole('button', { name: /reset password/i })
    expect(btn).toBeDisabled()
    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    expect(btn).not.toBeDisabled()
  })

  it('submits after confirm() — posts identifier to the reset-password endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_PASSWORD_RESET', temp_password: 'Tmp1234ABCD' } })
    const user = userEvent.setup()
    render(<EmployeePasswordReset />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/v1/org/employees/reset-password', { identifier: 'rahul@example.com' })
    })
  })

  it('cancelling the confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<EmployeePasswordReset />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    expect(mockPost).not.toHaveBeenCalled()
  })

  it('shows the success message and the generated temp password, then clears the input', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_PASSWORD_RESET', temp_password: 'Tmp1234ABCD' } })
    const user = userEvent.setup()
    render(<EmployeePasswordReset />, { wrapper })

    const input = screen.getByLabelText('Employee email or mobile number') as HTMLInputElement
    await user.type(input, 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    expect(await screen.findByText(/Password reset\./)).toBeInTheDocument()
    expect(screen.getByText('Tmp1234ABCD')).toBeInTheDocument()
    expect(input.value).toBe('')
  })

  it('shows the mapped error message when the employee is not found', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockRejectedValue({ response: { data: { detail: 'EMPLOYEE_NOT_FOUND' } } })
    const user = userEvent.setup()
    render(<EmployeePasswordReset />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'nobody@example.com')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    expect(await screen.findByText('Employee not found.')).toBeInTheDocument()
  })
})
