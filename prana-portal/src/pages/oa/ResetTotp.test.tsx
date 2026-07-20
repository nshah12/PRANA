/**
 * ResetTotp tests
 *
 *  1. Renders title, sub, and identifier input
 *  2. Submit button disabled until identifier is entered
 *  3. Submits after confirm() — posts to /v1/org/employees/reset-totp with identifier
 *  4. Cancelling confirm() does not call the API
 *  5. Success shows the mapped success message and clears the input
 *  6. API error (EMPLOYEE_NOT_FOUND) shows the mapped error message
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ResetTotp } from './ResetTotp'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('ResetTotp', () => {
  it('renders the title, sub, and identifier input', () => {
    render(<ResetTotp />, { wrapper })
    expect(screen.getByRole('heading', { name: 'Reset TOTP' })).toBeInTheDocument()
    expect(screen.getByText(/Reset an employee's two-factor authentication/)).toBeInTheDocument()
    expect(screen.getByLabelText('Employee email or mobile number')).toBeInTheDocument()
  })

  it('disables the submit button until an identifier is entered', async () => {
    const user = userEvent.setup()
    render(<ResetTotp />, { wrapper })

    const submitBtn = screen.getByRole('button', { name: /Reset TOTP/i })
    expect(submitBtn).toBeDisabled()

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    expect(submitBtn).not.toBeDisabled()
  })

  it('submits after confirm() — posts identifier to the reset-totp endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_TOTP_RESET' } })
    const user = userEvent.setup()
    render(<ResetTotp />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /Reset TOTP/i }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/v1/org/employees/reset-totp', { identifier: 'rahul@example.com' })
    })
  })

  it('cancelling the confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<ResetTotp />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /Reset TOTP/i }))

    expect(mockPost).not.toHaveBeenCalled()
  })

  it('shows a success message and clears the input on success', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_TOTP_RESET' } })
    const user = userEvent.setup()
    render(<ResetTotp />, { wrapper })

    const input = screen.getByLabelText('Employee email or mobile number') as HTMLInputElement
    await user.type(input, 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /Reset TOTP/i }))

    await waitFor(() => {
      expect(screen.getByText(/TOTP reset\./)).toBeInTheDocument()
    })
    expect(input.value).toBe('')
  })

  it('shows the mapped error message when the employee is not found', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockRejectedValue({ response: { data: { detail: 'EMPLOYEE_NOT_FOUND' } } })
    const user = userEvent.setup()
    render(<ResetTotp />, { wrapper })

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'nobody@example.com')
    await user.click(screen.getByRole('button', { name: /Reset TOTP/i }))

    await waitFor(() => {
      expect(screen.getByText('Employee not found.')).toBeInTheDocument()
    })
  })
})
