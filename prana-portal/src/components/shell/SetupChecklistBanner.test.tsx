/**
 * SetupChecklistBanner tests
 *
 * Contract (from src/components/shell/SetupChecklistBanner.tsx):
 *   <SetupChecklistBanner missingCount={2} top={52} />
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { SetupChecklistBanner } from './SetupChecklistBanner'

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

describe('SetupChecklistBanner', () => {
  it('shows the missing item count', () => {
    render(<SetupChecklistBanner missingCount={2} top={52} />, { wrapper })
    expect(screen.getByText(/2 required setup checklist item\(s\) incomplete/)).toBeInTheDocument()
  })

  it('links to the setup checklist page', () => {
    render(<SetupChecklistBanner missingCount={1} top={52} />, { wrapper })
    const link = screen.getByText('Complete checklist').closest('a')
    expect(link).toHaveAttribute('href', '/org/setup-checklist')
  })

  it('positions itself at the given top offset', () => {
    const { container } = render(<SetupChecklistBanner missingCount={1} top={92} />, { wrapper })
    const banner = container.firstChild as HTMLElement
    expect(banner.style.top).toBe('92px')
  })
})
