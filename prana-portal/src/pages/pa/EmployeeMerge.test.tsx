import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { EmployeeMerge } from './EmployeeMerge'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

beforeEach(() => vi.clearAllMocks())

describe('EmployeeMerge', () => {
  it('renders the title, warning, and all three fields', () => {
    render(<EmployeeMerge />)
    expect(screen.getByRole('heading', { name: 'Merge Duplicate Employee Records' })).toBeInTheDocument()
    expect(screen.getByText('PORTAL_ADMIN')).toBeInTheDocument()
    expect(screen.getByLabelText('Duplicate (will be merged away)')).toBeInTheDocument()
    expect(screen.getByLabelText('Canonical (will survive)')).toBeInTheDocument()
    expect(screen.getByLabelText(/Reason for override/)).toBeInTheDocument()
  })

  it('submits all three fields to the merge endpoint', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_RECORDS_MERGED', canonical_employee_user_id: 'eu-canonical' } })
    render(<EmployeeMerge />)

    await user.type(screen.getByLabelText('Duplicate (will be merged away)'), 'dup@example.com')
    await user.type(screen.getByLabelText('Canonical (will survive)'), 'canonical@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'PAN typo dedup')
    await user.click(screen.getByRole('button', { name: /merge records/i }))

    expect(mockPost).toHaveBeenCalledWith('/admin/employees/merge', {
      duplicate_identifier: 'dup@example.com',
      canonical_identifier: 'canonical@example.com',
      reason: 'PAN typo dedup',
    })
  })

  it('shows the mapped success message and clears the form', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_RECORDS_MERGED', canonical_employee_user_id: 'eu-canonical' } })
    render(<EmployeeMerge />)

    const dupInput = screen.getByLabelText('Duplicate (will be merged away)') as HTMLInputElement
    await user.type(dupInput, 'dup@example.com')
    await user.type(screen.getByLabelText('Canonical (will survive)'), 'canonical@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'PAN typo dedup')
    await user.click(screen.getByRole('button', { name: /merge records/i }))

    expect(await screen.findByText('Employee records merged.')).toBeInTheDocument()
    expect(dupInput.value).toBe('')
  })

  it('shows the mapped error message when both identifiers resolve to the same employee', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ response: { data: { detail: 'CANNOT_MERGE_SAME_EMPLOYEE' } } })
    render(<EmployeeMerge />)

    await user.type(screen.getByLabelText('Duplicate (will be merged away)'), 'same@example.com')
    await user.type(screen.getByLabelText('Canonical (will survive)'), 'same@example.com')
    await user.type(screen.getByLabelText(/Reason for override/), 'test')
    await user.click(screen.getByRole('button', { name: /merge records/i }))

    expect(await screen.findByText('The duplicate and canonical identifiers resolve to the same employee.')).toBeInTheDocument()
  })

  it('requires a reason before the browser allows submission', async () => {
    const user = userEvent.setup()
    render(<EmployeeMerge />)

    await user.type(screen.getByLabelText('Duplicate (will be merged away)'), 'dup@example.com')
    await user.type(screen.getByLabelText('Canonical (will survive)'), 'canonical@example.com')
    await user.click(screen.getByRole('button', { name: /merge records/i }))

    expect(mockPost).not.toHaveBeenCalled()
  })
})
