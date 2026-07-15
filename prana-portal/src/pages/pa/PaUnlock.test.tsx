import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PaUnlock } from './PaUnlock'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('PaUnlock', () => {
  it('renders the title and email field', () => {
    render(<PaUnlock />, { wrapper })
    expect(screen.getByRole('heading', { name: 'Unlock PA Account' })).toBeInTheDocument()
    expect(screen.getByLabelText("Locked PA's email")).toBeInTheDocument()
  })

  it('disables submit until an email is entered', async () => {
    const user = userEvent.setup()
    render(<PaUnlock />, { wrapper })
    const btn = screen.getByRole('button', { name: /unlock account/i })
    expect(btn).toBeDisabled()
    await user.type(screen.getByLabelText("Locked PA's email"), 'locked@prana.in')
    expect(btn).not.toBeDisabled()
  })

  it('submits after confirm() and posts to the unlock endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'LOCK_REMOVED' } })
    const user = userEvent.setup()
    render(<PaUnlock />, { wrapper })

    await user.type(screen.getByLabelText("Locked PA's email"), 'locked@prana.in')
    await user.click(screen.getByRole('button', { name: /unlock account/i }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/admin/pa-users/unlock', { email: 'locked@prana.in' })
    })
  })

  it('cancelling the confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<PaUnlock />, { wrapper })

    await user.type(screen.getByLabelText("Locked PA's email"), 'locked@prana.in')
    await user.click(screen.getByRole('button', { name: /unlock account/i }))

    expect(mockPost).not.toHaveBeenCalled()
  })

  it('shows the mapped success message and clears the field', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockResolvedValue({ data: { message: 'LOCK_REMOVED' } })
    const user = userEvent.setup()
    render(<PaUnlock />, { wrapper })

    const input = screen.getByLabelText("Locked PA's email") as HTMLInputElement
    await user.type(input, 'locked@prana.in')
    await user.click(screen.getByRole('button', { name: /unlock account/i }))

    expect(await screen.findByText('Account unlocked.')).toBeInTheDocument()
    expect(input.value).toBe('')
  })

  it('shows the mapped error message when the PA is not found', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockPost.mockRejectedValue({ response: { data: { detail: 'USER_NOT_FOUND' } } })
    const user = userEvent.setup()
    render(<PaUnlock />, { wrapper })

    await user.type(screen.getByLabelText("Locked PA's email"), 'nobody@prana.in')
    await user.click(screen.getByRole('button', { name: /unlock account/i }))

    expect(await screen.findByText('No account found with these details.')).toBeInTheDocument()
  })
})
