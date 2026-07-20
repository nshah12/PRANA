import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { EmployeeTotpReset } from './EmployeeTotpReset'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

beforeEach(() => vi.clearAllMocks())

describe('EmployeeTotpReset', () => {
  it('renders the title, override warning, and both required fields', () => {
    render(<EmployeeTotpReset />)
    expect(screen.getByRole('heading', { name: 'Reset Employee TOTP' })).toBeInTheDocument()
    expect(screen.getByText('PORTAL_ADMIN')).toBeInTheDocument()
    expect(screen.getByLabelText('Employee email or mobile number')).toBeInTheDocument()
    expect(screen.getByLabelText(/Reason for override/)).toBeInTheDocument()
  })

  it('submits identifier and reason to the PA reset-totp endpoint', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_TOTP_RESET' } })
    render(<EmployeeTotpReset />)

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'Support escalation TCK-1234')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/admin/employees/reset-totp', {
        identifier: 'rahul@example.com',
        reason: 'Support escalation TCK-1234',
      })
    })
  })

  it('shows the mapped success message and clears the form on success', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_TOTP_RESET' } })
    render(<EmployeeTotpReset />)

    const identifierInput = screen.getByLabelText('Employee email or mobile number') as HTMLInputElement
    await user.type(identifierInput, 'rahul@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'Support escalation TCK-1234')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    expect(await screen.findByText(/TOTP reset\./)).toBeInTheDocument()
    expect(identifierInput.value).toBe('')
  })

  it('shows the mapped error message on failure', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ response: { data: { detail: 'EMPLOYEE_NOT_FOUND' } } })
    render(<EmployeeTotpReset />)

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'nobody@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'Support escalation TCK-1234')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    expect(await screen.findByText('Employee not found.')).toBeInTheDocument()
  })

  it('requires a reason before the browser allows submission', async () => {
    const user = userEvent.setup()
    render(<EmployeeTotpReset />)

    await user.type(screen.getByLabelText('Employee email or mobile number'), 'rahul@example.com')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    expect(mockPost).not.toHaveBeenCalled()
  })
})
