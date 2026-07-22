import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { OverrideReasonFields } from './OverrideReasonFields'

function Harness() {
  const [reasonCode, setReasonCode] = useState('')
  const [reasonNote, setReasonNote] = useState('')
  return (
    <OverrideReasonFields
      idPrefix="test"
      reasonCode={reasonCode}
      reasonNote={reasonNote}
      onReasonCodeChange={setReasonCode}
      onReasonNoteChange={setReasonNote}
    />
  )
}

describe('OverrideReasonFields', () => {
  it('renders a reason dropdown and an optional note field', () => {
    render(<Harness />)
    expect(screen.getByRole('combobox', { name: /reason for override/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/additional detail/i)).not.toBeRequired()
  })

  it('lists all canonical reason codes as options', () => {
    render(<Harness />)
    const select = screen.getByRole('combobox', { name: /reason for override/i })
    expect(select).toHaveTextContent('Support escalation')
    expect(select).toHaveTextContent('Employee lost device')
    expect(select).toHaveTextContent('Security incident')
    expect(select).toHaveTextContent('Compliance / legal request')
    expect(select).toHaveTextContent('Other')
  })

  it('makes the note field required once "Other" is selected', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const select = screen.getByRole('combobox', { name: /reason for override/i })
    await user.selectOptions(select, 'OTHER')
    expect(screen.getByLabelText(/additional detail/i)).toBeRequired()
  })

  it('calls onReasonCodeChange when a reason is picked', async () => {
    const user = userEvent.setup()
    const onReasonCodeChange = vi.fn()
    render(
      <OverrideReasonFields
        idPrefix="test"
        reasonCode=""
        reasonNote=""
        onReasonCodeChange={onReasonCodeChange}
        onReasonNoteChange={() => {}}
      />,
    )
    await user.selectOptions(screen.getByRole('combobox', { name: /reason for override/i }), 'SECURITY_INCIDENT')
    expect(onReasonCodeChange).toHaveBeenCalledWith('SECURITY_INCIDENT')
  })
})
