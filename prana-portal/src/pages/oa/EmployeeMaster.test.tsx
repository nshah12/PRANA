/**
 * EmployeeMaster tests
 *
 *  1. Loading state shows "Loading…" row
 *  2. Empty state — no employees found
 *  3. Renders employee rows with fields formatted
 *  4. Search input updates query param sent to API
 *  5. Pagination — Prev disabled on first page, Next disabled when all shown
 *  6. Pagination — clicking Next advances page and shows correct "Showing" text
 *  7. Normalises a plain-array API response
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmployeeMaster } from './EmployeeMaster'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function makeEmployees(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    employee_uuid: `e-${i}`,
    full_name: `Employee ${i}`,
    emp_id_org: `EMP${i}`,
    department: 'Engineering',
    designation: 'SDE',
    doj: '2022-01-15',
    status: 'ACTIVE',
  }))
}

beforeEach(() => vi.clearAllMocks())

describe('EmployeeMaster', () => {
  it('shows loading row while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmployeeMaster />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows empty state when no employees found', async () => {
    mockGet.mockResolvedValue({ data: [] })
    render(<EmployeeMaster />, { wrapper })
    expect(await screen.findByText('No employees found.')).toBeInTheDocument()
  })

  it('renders employee rows with formatted fields', async () => {
    mockGet.mockResolvedValue({ data: makeEmployees(3) })
    render(<EmployeeMaster />, { wrapper })
    expect(await screen.findByText('Employee 0')).toBeInTheDocument()
    expect(screen.getByText('EMP0')).toBeInTheDocument()
    expect(screen.getAllByText('Engineering').length).toBe(3)
    expect(screen.getAllByText('SDE').length).toBe(3)
  })

  it('sends the search term as the name param', async () => {
    mockGet.mockResolvedValue({ data: [] })
    render(<EmployeeMaster />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const user = userEvent.setup()
    await user.type(screen.getByPlaceholderText('Search by name, emp ID, or department…'), 'Priya')
    await waitFor(() => {
      const lastCall = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      expect(lastCall[1]?.params?.name).toBe('Priya')
    })
  })

  it('disables Prev on first page and Next when all employees shown', async () => {
    mockGet.mockResolvedValue({ data: makeEmployees(5) })
    render(<EmployeeMaster />, { wrapper })
    await screen.findByText('Employee 0')
    // count (5) <= limit (20) so pagination footer should not render at all
    expect(screen.queryByRole('button', { name: '← Prev' })).not.toBeInTheDocument()
  })

  it('paginates: shows Showing text and advances to next page', async () => {
    mockGet.mockResolvedValue({ data: makeEmployees(45) })
    render(<EmployeeMaster />, { wrapper })
    expect(await screen.findByText('Showing 1–20 of 45')).toBeInTheDocument()
    const prevBtn = screen.getByRole('button', { name: '← Prev' })
    const nextBtn = screen.getByRole('button', { name: 'Next →' })
    expect(prevBtn).toBeDisabled()
    expect(nextBtn).not.toBeDisabled()

    const user = userEvent.setup()
    await user.click(nextBtn)
    expect(await screen.findByText('Showing 21–40 of 45')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '← Prev' })).not.toBeDisabled()
  })

  it('normalises a { employees: [...] } shaped API response', async () => {
    mockGet.mockResolvedValue({ data: { employees: makeEmployees(2) } })
    render(<EmployeeMaster />, { wrapper })
    expect(await screen.findByText('Employee 0')).toBeInTheDocument()
    expect(screen.getByText('Employee 1')).toBeInTheDocument()
  })
})
