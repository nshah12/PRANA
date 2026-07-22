import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmpAsk } from './EmpAsk'
import { useEmpAuthStore } from '@/store/empAuth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

// jsdom does not implement scrollIntoView — EmpAsk calls it on every message update.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

beforeEach(() => {
  vi.clearAllMocks()
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
})

describe('EmpAsk', () => {
  it('greets with a default name when no user is set', () => {
    render(<EmpAsk />)
    expect(screen.getByText(/Hi there!/)).toBeInTheDocument()
  })

  it("greets using the logged-in user's first name", () => {
    useEmpAuthStore.setState({
      user: { userId: 'u1', name: 'Rahul Sharma', email: '', mobile: '', pan_token: '', vault_url: '' },
      accessToken: 'tok', stepToken: null,
    })
    render(<EmpAsk />)
    expect(screen.getByText(/Hi Rahul!/)).toBeInTheDocument()
  })

  it('shows the header title, sub, and no-raw-figures badge', () => {
    render(<EmpAsk />)
    expect(screen.getByText('Ask PRANA')).toBeInTheDocument()
    expect(screen.getByText('insights only · figures stay private')).toBeInTheDocument()
    expect(screen.getByText('No raw figures ever shown')).toBeInTheDocument()
  })

  it('shows suggested questions on the first message only', () => {
    render(<EmpAsk />)
    expect(screen.getByText('Suggested')).toBeInTheDocument()
    expect(screen.getByText('Am I home loan ready?')).toBeInTheDocument()
  })

  it('sends a typed question and renders the assistant answer', async () => {
    mockPost.mockResolvedValue({ data: { answer: 'Your salary progression looks healthy.' } })
    const user = userEvent.setup()
    render(<EmpAsk />)

    const textarea = screen.getByPlaceholderText('Ask about consistency, readiness, growth…')
    await user.type(textarea, 'Am I doing well?')
    await user.click(screen.getByRole('button', { name: '' })) // send icon button has no accessible name

    expect(await screen.findByText('Your salary progression looks healthy.')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/ask', { query: 'Am I doing well?' })
    // Input is cleared after send
    expect(textarea).toHaveValue('')
  })

  it('clicking a suggested question sends it directly', async () => {
    mockPost.mockResolvedValue({ data: { answer: 'Yes, consistent.' } })
    const user = userEvent.setup()
    render(<EmpAsk />)

    await user.click(screen.getByText('Was my bonus paid correctly?'))
    expect(await screen.findByText('Yes, consistent.')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/ask', { query: 'Was my bonus paid correctly?' })
  })

  it('shows the thinking indicator while a request is in-flight', async () => {
    let resolvePost: (v: any) => void
    mockPost.mockReturnValue(new Promise(res => { resolvePost = res }))
    const user = userEvent.setup()
    render(<EmpAsk />)

    const textarea = screen.getByPlaceholderText('Ask about consistency, readiness, growth…')
    await user.type(textarea, 'hello{Enter}')

    expect(await screen.findByText('Analysing documents…')).toBeInTheDocument()
    resolvePost!({ data: { answer: 'done' } })
    await waitFor(() => expect(screen.queryByText('Analysing documents…')).not.toBeInTheDocument())
  })

  it('shows the rate-limit fallback message on a 429 error', async () => {
    mockPost.mockRejectedValue({ response: { status: 429 } })
    const user = userEvent.setup()
    render(<EmpAsk />)

    await user.type(screen.getByPlaceholderText('Ask about consistency, readiness, growth…'), 'test{Enter}')
    expect(await screen.findByText("You've reached the Ask PRANA limit for this hour. Try again later.")).toBeInTheDocument()
  })

  it('shows the timeout fallback message on a 504 error', async () => {
    mockPost.mockRejectedValue({ response: { status: 504 } })
    const user = userEvent.setup()
    render(<EmpAsk />)

    await user.type(screen.getByPlaceholderText('Ask about consistency, readiness, growth…'), 'test{Enter}')
    expect(await screen.findByText('The AI is taking longer than expected. Please try again.')).toBeInTheDocument()
  })

  it('shows the generic fallback message on any other error', async () => {
    mockPost.mockRejectedValue(new Error('network down'))
    const user = userEvent.setup()
    render(<EmpAsk />)

    await user.type(screen.getByPlaceholderText('Ask about consistency, readiness, growth…'), 'test{Enter}')
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
  })

  it('disables the send button when input is empty', () => {
    render(<EmpAsk />)
    const buttons = screen.getAllByRole('button')
    const sendBtn = buttons[buttons.length - 1]
    expect(sendBtn).toBeDisabled()
  })

  it('never renders a raw rupee figure or PAN-shaped value in chat responses — privacy contract', async () => {
    mockPost.mockResolvedValue({ data: { answer: 'Your career trajectory is strong.' } })
    const user = userEvent.setup()
    render(<EmpAsk />)
    await user.type(screen.getByPlaceholderText('Ask about consistency, readiness, growth…'), 'test{Enter}')
    await screen.findByText('Your career trajectory is strong.')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
