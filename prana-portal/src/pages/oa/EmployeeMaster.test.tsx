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

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

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

  // -- Reactivate (un-mark alumni) ----------------------------------------------

  it('shows a Reactivate button only for ALUMNI-status rows', async () => {
    mockGet.mockResolvedValue({
      data: [
        { ...makeEmployees(1)[0], status: 'ACTIVE' },
        { ...makeEmployees(1)[0], employee_uuid: 'e-alumni', full_name: 'Alumni Person', status: 'ALUMNI' },
      ],
    })
    render(<EmployeeMaster />, { wrapper })
    await screen.findByText('Employee 0')
    expect(screen.getAllByText('Reactivate').length).toBe(1)
  })

  it('reactivating requires confirmation, then posts to the reactivate endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    mockGet.mockResolvedValue({
      data: [{ ...makeEmployees(1)[0], employee_uuid: 'e-alumni', full_name: 'Alumni Person', status: 'ALUMNI' }],
    })
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_REACTIVATED' } })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Reactivate'))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/v1/org/employees/e-alumni/reactivate')
    })
    expect(window.alert).toHaveBeenCalledWith('Employee reactivated.')
  })

  it('cancelling the confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockGet.mockResolvedValue({
      data: [{ ...makeEmployees(1)[0], employee_uuid: 'e-alumni', full_name: 'Alumni Person', status: 'ALUMNI' }],
    })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Reactivate'))

    expect(mockPost).not.toHaveBeenCalled()
  })

  // -- Bulk revoke sessions ("sign out everywhere") -----------------------------

  it('shows a "Sign out everywhere" action for every employee regardless of status', async () => {
    mockGet.mockResolvedValue({ data: makeEmployees(2) })
    render(<EmployeeMaster />, { wrapper })
    await screen.findByText('Employee 0')
    expect(screen.getAllByText('Sign out everywhere').length).toBe(2)
  })

  it('signing out requires confirmation, then posts to the revoke-sessions endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    mockGet.mockResolvedValue({ data: makeEmployees(1) })
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_SESSIONS_REVOKED', revoked_count: 2 } })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Sign out everywhere'))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/v1/org/employees/e-0/revoke-sessions')
    })
    expect(window.alert).toHaveBeenCalledWith('Employee signed out of all devices.')
  })

  it('cancelling the sign-out confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockGet.mockResolvedValue({ data: makeEmployees(1) })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Sign out everywhere'))

    expect(mockPost).not.toHaveBeenCalled()
  })

  // -- Bulk revoke share links ---------------------------------------------------

  it('shows a "Revoke all shares" action for every employee', async () => {
    mockGet.mockResolvedValue({ data: makeEmployees(2) })
    render(<EmployeeMaster />, { wrapper })
    await screen.findByText('Employee 0')
    expect(screen.getAllByText('Revoke all shares').length).toBe(2)
  })

  it('revoking shares requires confirmation, then posts to the revoke-shares endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    mockGet.mockResolvedValue({ data: makeEmployees(1) })
    mockPost.mockResolvedValue({ data: { message: 'EMPLOYEE_SHARES_REVOKED', revoked_count: 3 } })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Revoke all shares'))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/v1/org/employees/e-0/revoke-shares')
    })
    expect(window.alert).toHaveBeenCalledWith('All active share links for this employee have been revoked.')
  })

  it('cancelling the revoke-shares confirm dialog does not call the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockGet.mockResolvedValue({ data: makeEmployees(1) })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(await screen.findByText('Revoke all shares'))

    expect(mockPost).not.toHaveBeenCalled()
  })

  // -- Bulk CSV import -----------------------------------------------------------

  it('opens the bulk-import modal when "Bulk upload CSV" is clicked', async () => {
    mockGet.mockResolvedValue({ data: [] })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(screen.getByText('Bulk upload CSV'))

    expect(screen.getByLabelText('Employee CSV file')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
  })

  it('uploads the selected file and shows the created/failed summary', async () => {
    mockGet.mockResolvedValue({ data: [] })
    mockPost.mockResolvedValue({
      data: { total: 2, created: 1, failed: 1, errors: [{ row: 3, error: 'CSV_INVALID_DATE_FORMAT' }] },
    })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(screen.getByText('Bulk upload CSV'))
    const file = new File(['nik,full_name,doj\nA,B,2022-01-01\n'], 'employees.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Employee CSV file'), file)
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/v1/org/employees/import')
    expect(body).toBeInstanceOf(FormData)

    expect(await screen.findByText(/1 of 2 created \(1 failed\)\./)).toBeInTheDocument()
    expect(screen.getByText('Invalid date format for doj — use YYYY-MM-DD.')).toBeInTheDocument()
  })

  it('disables the Upload button until a file is chosen', async () => {
    mockGet.mockResolvedValue({ data: [] })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(screen.getByText('Bulk upload CSV'))
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('shows the mapped error message when the whole upload is rejected', async () => {
    mockGet.mockResolvedValue({ data: [] })
    mockPost.mockRejectedValue({ response: { data: { detail: 'CSV_MISSING_REQUIRED_COLUMNS' } } })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(screen.getByText('Bulk upload CSV'))
    const file = new File(['full_name\nB\n'], 'employees.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Employee CSV file'), file)
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByText('The CSV is missing required columns: nik, full_name, doj.')).toBeInTheDocument()
  })

  it('closes the modal via Cancel without uploading', async () => {
    mockGet.mockResolvedValue({ data: [] })
    const user = userEvent.setup()
    render(<EmployeeMaster />, { wrapper })

    await user.click(screen.getByText('Bulk upload CSV'))
    await user.click(screen.getByText('Cancel'))

    expect(screen.queryByLabelText('Employee CSV file')).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
