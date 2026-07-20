import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { OaEmergency } from './OaEmergency'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

beforeEach(() => vi.clearAllMocks())

describe('OaEmergency', () => {
  it('shows no form until an action is selected', () => {
    render(<OaEmergency />)
    expect(screen.queryByRole('button', { name: /execute override/i })).not.toBeInTheDocument()
  })

  it('shows the create-OA form when Create OA is selected', async () => {
    const user = userEvent.setup()
    render(<OaEmergency />)
    await user.click(screen.getByRole('button', { name: /^create oa$/i }))
    expect(screen.getByRole('button', { name: /execute override/i })).toBeInTheDocument()
  })

  it('submits the emergency action and shows the success message', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { message: 'OA account created' } })
    render(<OaEmergency />)
    await user.click(screen.getByRole('button', { name: /^create oa$/i }))

    const labels = screen.getAllByRole('textbox')
    await user.type(labels[0], 'oa@acme.in')
    await user.type(labels[1], 'acme.in')
    await user.type(labels[2], 'Emergency account creation — OA-Admin locked out')

    await user.click(screen.getByRole('button', { name: /execute override/i }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/oa-emergency/create', {
      email: 'oa@acme.in', tenant_domain: 'acme.in', reason: 'Emergency account creation — OA-Admin locked out',
    }))
    expect(await screen.findByText('OA account created')).toBeInTheDocument()
  })

  it('shows the server error detail on failure', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ response: { data: { detail: 'TENANT_NOT_FOUND' } } })
    render(<OaEmergency />)
    await user.click(screen.getByRole('button', { name: /^suspend oa$/i }))

    const labels = screen.getAllByRole('textbox')
    await user.type(labels[1], 'unknown.in')
    await user.type(labels[2], 'Suspend compromised account')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    expect(await screen.findByText('TENANT_NOT_FOUND')).toBeInTheDocument()
  })

  it('falls back to a generic failure message when no detail is present', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('network error'))
    render(<OaEmergency />)
    await user.click(screen.getByRole('button', { name: /^reset oa$/i }))

    const labels = screen.getAllByRole('textbox')
    await user.type(labels[1], 'acme.in')
    await user.type(labels[2], 'Reset password for locked OA account')
    await user.click(screen.getByRole('button', { name: /execute override/i }))

    expect(await screen.findByText('Failed')).toBeInTheDocument()
  })
})
