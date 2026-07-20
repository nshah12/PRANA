/**
 * HRMSSettings tests
 *
 *  1. Loading state while fetching configs
 *  2. Error state when configs fail to load
 *  3. Empty state — no HRMS connected yet
 *  4. Renders connector cards with status pill and last synced text
 *  5. Test connection button shows success/failure result
 *  6. Sync now button calls sync mutation
 *  7. Pause / Resume flip based on status
 *  8. Sync history expands and shows log rows / empty message
 *  9. Add connector form: fills fields and saves; shows save-failed message on error
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { HRMSSettings } from './HRMSSettings'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const DEFS = [
  { connector_definition_id: 'def-1', connector_key: 'DARWINBOX', display_name: 'Darwinbox', auth_method: 'OAUTH2', supported_modes: ['PULL', 'PUSH'] },
]

function makeConfig(overrides: Partial<any> = {}) {
  return {
    connector_id: 'c-1',
    display_name: 'Acme Darwinbox',
    connector_key: 'DARWINBOX',
    integration_mode: 'PULL',
    status: 'ACTIVE',
    last_pulled_at: '2024-06-01T10:00:00Z',
    ...overrides,
  }
}

function mockGets({ configs = [makeConfig()], configError = false }: { configs?: any[]; configError?: boolean } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/admin/hrms/definitions')) return Promise.resolve({ data: { items: DEFS } })
    if (url.includes('/sync-log')) return Promise.resolve({ data: { items: [] } })
    if (url === '/hrms/config') {
      return configError ? Promise.reject(new Error('boom')) : Promise.resolve({ data: { items: configs } })
    }
    return Promise.resolve({ data: {} })
  })
}

beforeEach(() => vi.clearAllMocks())

describe('HRMSSettings', () => {
  it('shows loading state while fetching connectors', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<HRMSSettings />, { wrapper })
    expect(screen.getByText('Loading connectors…')).toBeInTheDocument()
  })

  it('shows error state when configs fail to load', async () => {
    mockGets({ configError: true })
    render(<HRMSSettings />, { wrapper })
    expect(await screen.findByText('Failed to load HRMS configuration.')).toBeInTheDocument()
  })

  it('shows empty state when no HRMS connected', async () => {
    mockGets({ configs: [] })
    render(<HRMSSettings />, { wrapper })
    expect(await screen.findByText('No HRMS connected yet')).toBeInTheDocument()
    expect(screen.getByText('Click "Add connector" to sync employee records automatically.')).toBeInTheDocument()
  })

  it('renders a connector card with status, auth method and last synced time', async () => {
    mockGets()
    render(<HRMSSettings />, { wrapper })
    expect(await screen.findByText('Acme Darwinbox')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('OAUTH2')).toBeInTheDocument()
    expect(screen.getByText(/Last synced:/)).toBeInTheDocument()
  })

  it('test connection shows success result', async () => {
    mockGets()
    mockPost.mockResolvedValue({ data: { ok: true } })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(await screen.findByText('Connection successful')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/hrms/config/c-1/test')
  })

  it('test connection shows failure result on error', async () => {
    mockGets()
    mockPost.mockRejectedValue(new Error('bad creds'))
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(await screen.findByText('Connection failed — check credentials')).toBeInTheDocument()
  })

  it('sync now calls the sync mutation for an ACTIVE connector', async () => {
    mockGets()
    mockPost.mockResolvedValue({ data: {} })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Sync now' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/hrms/config/c-1/sync'))
  })

  it('shows Pause for ACTIVE and Resume for PAUSED connectors', async () => {
    mockGets({ configs: [makeConfig({ status: 'ACTIVE' })] })
    const { unmount } = render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
    unmount()

    mockGets({ configs: [makeConfig({ status: 'PAUSED', connector_id: 'c-2' })] })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')
    expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument()
  })

  it('pause calls the pause endpoint', async () => {
    mockGets()
    mockPatch.mockResolvedValue({ data: {} })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Pause' }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/hrms/config/c-1/pause'))
  })

  it('expands sync history and shows the empty-history message', async () => {
    mockGets()
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Sync history/ }))

    expect(await screen.findByText('No sync history yet.')).toBeInTheDocument()
  })

  it('shows sync history log rows when present', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/admin/hrms/definitions')) return Promise.resolve({ data: { items: DEFS } })
      if (url.includes('/sync-log')) {
        return Promise.resolve({ data: { items: [{ sync_id: 's-1', status: 'SUCCESS', docs_pushed: 5, docs_failed: 0, started_at: '2024-06-01T09:00:00Z' }] } })
      }
      if (url === '/hrms/config') return Promise.resolve({ data: { items: [makeConfig()] } })
      return Promise.resolve({ data: {} })
    })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('Acme Darwinbox')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Sync history/ }))

    expect(await screen.findByText('5 pushed · 0 failed')).toBeInTheDocument()
  })

  it('opens the add-connector form, fills fields, and saves', async () => {
    mockGets({ configs: [] })
    mockPost.mockResolvedValue({ data: {} })
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('No HRMS connected yet')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Add connector' }))
    expect(screen.getByText('Connect an HRMS')).toBeInTheDocument()

    await user.selectOptions(screen.getAllByRole('combobox')[0], 'def-1')
    await user.click(screen.getByRole('button', { name: 'Save connector' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/hrms/config', expect.objectContaining({
      connector_definition_id: 'def-1',
      display_name: 'Darwinbox',
    })))
  })

  it('shows save-failed message when connector creation errors', async () => {
    mockGets({ configs: [] })
    mockPost.mockRejectedValue(new Error('fail'))
    render(<HRMSSettings />, { wrapper })
    await screen.findByText('No HRMS connected yet')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Add connector' }))
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'def-1')
    await user.click(screen.getByRole('button', { name: 'Save connector' }))

    expect(await screen.findByText('Failed to save. Check credentials JSON and try again.')).toBeInTheDocument()
  })
})
