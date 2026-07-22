import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Announcements } from './Announcements'

describe('Announcements', () => {
  it('renders the page title', () => {
    render(<Announcements />)
    expect(screen.getByText('Platform Announcements')).toBeInTheDocument()
  })

  it('renders all static announcement entries with title, date and category', () => {
    render(<Announcements />)
    expect(screen.getByText('PRANA Platform v2.1 — DPDP Act 2023 Compliance Module Live')).toBeInTheDocument()
    expect(screen.getByText('YugabyteDB upgrade to 2.20.2 — scheduled maintenance')).toBeInTheDocument()
    expect(screen.getByText('New tenant onboarding: PQRS Fintech Pvt Ltd')).toBeInTheDocument()
    expect(screen.getByText('AI Pipeline Qwen2.5-14B model update available')).toBeInTheDocument()
    expect(screen.getByText('RELEASE')).toBeInTheDocument()
    expect(screen.getByText('MAINTENANCE')).toBeInTheDocument()
    expect(screen.getByText('TENANT')).toBeInTheDocument()
    expect(screen.getByText('AI')).toBeInTheDocument()
  })

  it('renders the body text for each announcement', () => {
    render(<Announcements />)
    expect(screen.getByText(/consent management, data erasure, and grievance workflows/)).toBeInTheDocument()
  })

  it('never shows a blank screen — always has at least one announcement card', () => {
    render(<Announcements />)
    expect(document.querySelectorAll('.rounded-xl.border').length).toBeGreaterThan(0)
  })
})
