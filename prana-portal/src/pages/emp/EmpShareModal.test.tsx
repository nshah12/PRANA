import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmpShareModal } from './EmpShareModal'

describe('EmpShareModal', () => {
  it('renders the single-document share title and truncated document id', () => {
    render(<EmpShareModal documentId="d1234567-89ab-cdef-0123-456789abcdef" onClose={() => {}} />)
    expect(screen.getByText('Share Document')).toBeInTheDocument()
    expect(screen.getByText(/Create a time-limited shareable link for document d1234567…/)).toBeInTheDocument()
  })

  it('renders the bulk share title and copy when documentId is "bulk"', () => {
    render(<EmpShareModal documentId="bulk" onClose={() => {}} />)
    expect(screen.getByText('Share Documents')).toBeInTheDocument()
    expect(screen.getByText('Select documents and create a shareable link below.')).toBeInTheDocument()
  })

  it('calls onClose when the X icon button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EmpShareModal documentId="d1" onClose={onClose} />)

    // The X button is the first button in the header (no accessible name — icon only)
    const buttons = screen.getAllByRole('button')
    await user.click(buttons[0])
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EmpShareModal documentId="d1" onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Create Share Link is clicked (no real share creation wired up yet)', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<EmpShareModal documentId="d1" onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Create Share Link' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('never renders a raw rupee figure or PAN-shaped value — privacy contract', () => {
    render(<EmpShareModal documentId="d1234567-89ab-cdef-0123-456789abcdef" onClose={() => {}} />)
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
