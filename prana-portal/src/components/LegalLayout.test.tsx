/**
 * LegalLayout tests
 *
 * Contract under test (from src/components/LegalLayout.tsx):
 *  1. Renders the title, and the badge (defaults to "Legal" when not passed)
 *  2. Renders the subtitle only when provided
 *  3. Renders children content
 *  4. Renders the footer link sections + copyright
 *  5. "Back to home" and the brand mark both navigate to "/"
 *
 * LegalLayout is used directly by the legal pages (src/pages/legal/*), each passing
 * title/subtitle/badge/children — no other props flow in.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...(actual as any), useNavigate: () => mockNavigate }
})

import { LegalLayout } from './LegalLayout'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LegalLayout', () => {
  it('renders the title and defaults the badge to "Legal"', () => {
    render(<LegalLayout title="Privacy Policy">content</LegalLayout>)
    expect(screen.getByRole('heading', { name: 'Privacy Policy' })).toBeInTheDocument()
    // "Legal" also appears as a footer section heading (FOOTER_LINKS.Legal), and
    // .text-indigo-500 also matches the nav brand mark's "·" separator (which
    // comes first in DOM order) — the badge is the one span with BOTH
    // text-indigo-500 AND uppercase, distinguishing it from both.
    expect(document.querySelector('span.text-indigo-500.uppercase')?.textContent).toBe('Legal')
  })

  it('renders a custom badge when provided', () => {
    render(<LegalLayout title="API Terms" badge="Developer">content</LegalLayout>)
    expect(document.querySelector('span.text-indigo-500.uppercase')?.textContent).toBe('Developer')
    // The footer's "Legal" section heading is unrelated to the badge prop and
    // always renders — only the badge itself (indigo span) should change.
  })

  it('renders the subtitle only when provided', () => {
    const { rerender } = render(<LegalLayout title="Terms of Use" subtitle="Effective 1 Jan 2026">content</LegalLayout>)
    expect(screen.getByText('Effective 1 Jan 2026')).toBeInTheDocument()

    rerender(<LegalLayout title="Terms of Use">content</LegalLayout>)
    expect(screen.queryByText('Effective 1 Jan 2026')).not.toBeInTheDocument()
  })

  it('renders children content', () => {
    render(<LegalLayout title="DPA"><p>Data processing details go here.</p></LegalLayout>)
    expect(screen.getByText('Data processing details go here.')).toBeInTheDocument()
  })

  it('renders the footer link section headings and copyright', () => {
    render(<LegalLayout title="Cookie Policy">content</LegalLayout>)
    expect(screen.getByText('Product')).toBeInTheDocument()
    expect(screen.getByText('For Organisations')).toBeInTheDocument()
    expect(screen.getByText('Company')).toBeInTheDocument()
    // "Legal" appears both as the default badge and as a footer heading — scope with getAllByText
    expect(screen.getAllByText('Legal').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/PRANA Technologies Pvt Ltd/)).toBeInTheDocument()
  })

  it('navigates home when the brand mark is clicked', async () => {
    const user = userEvent.setup()
    render(<LegalLayout title="Grievance Redressal">content</LegalLayout>)
    // "PRANA" also appears in the footer brand mark, which is a plain <a href="/">
    // (full page nav, not a React Router navigate() call) — only the nav's
    // clickable <button> should invoke mockNavigate.
    await user.click(screen.getByRole('button', { name: /PRANA/ }))
    expect(mockNavigate).toHaveBeenCalledWith('/')
  })

  it('navigates home when "Back to home" is clicked', async () => {
    const user = userEvent.setup()
    render(<LegalLayout title="Grievance Redressal">content</LegalLayout>)
    await user.click(screen.getByText(/back to home/i))
    expect(mockNavigate).toHaveBeenCalledWith('/')
  })
})
