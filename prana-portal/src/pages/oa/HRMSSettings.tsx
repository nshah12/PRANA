import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Plug, Play, Pause, TestTube2, RefreshCw,
  CheckCircle2, XCircle, Loader2, AlertCircle, ChevronDown,
} from 'lucide-react'
import { api } from '@/lib/api'

interface ConnectorConfig {
  connector_id:    string
  display_name:    string
  connector_key:   string
  integration_mode: string
  status:          string
  pull_schedule?:  string
  last_pulled_at?: string
  last_sync_at?:   string
}

interface ConnectorDef {
  connector_definition_id: string
  connector_key: string
  display_name:  string
  auth_method:   string
  supported_modes: string[]
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ACTIVE:  'bg-emerald-50 text-emerald-700 border-emerald-200',
    PAUSED:  'bg-amber-50  text-amber-700  border-amber-200',
    REVOKED: 'bg-red-50    text-red-700    border-red-200',
  }
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${map[status] ?? 'bg-slate-50 text-slate-500 border-slate-200'}`}>
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  )
}

function SyncHistory({ connectorId }: { connectorId: string }) {
  const { data, isLoading } = useQuery({
    queryKey:  ['hrms-sync-log', connectorId],
    queryFn:   () => api.get(`/hrms/config/${connectorId}/sync-log`).then(r => r.data),
    staleTime: 30_000,
  })

  if (isLoading) return <p className="text-xs text-slate-400">Loading history…</p>

  const logs = data?.items ?? []
  if (!logs.length) return <p className="text-xs text-slate-400">No sync history yet.</p>

  return (
    <div className="divide-y divide-slate-100">
      {logs.slice(0, 5).map((l: any) => (
        <div key={l.sync_id} className="flex items-center justify-between py-1.5 text-xs">
          <span className={l.status === 'SUCCESS' ? 'text-emerald-600' : l.status === 'PARTIAL' ? 'text-amber-600' : 'text-red-500'}>
            {l.status}
          </span>
          <span className="text-slate-400">{l.docs_pushed} pushed · {l.docs_failed} failed</span>
          <span className="text-slate-400">{l.started_at ? new Date(l.started_at).toLocaleString() : '—'}</span>
        </div>
      ))}
    </div>
  )
}

function ConnectorCard({ cfg, defs }: { cfg: ConnectorConfig; defs: ConnectorDef[] }) {
  const qc = useQueryClient()
  const [showHistory, setShowHistory] = useState(false)
  const [testResult, setTestResult]   = useState<null | boolean>(null)

  const pauseMut = useMutation({
    mutationFn: () => api.patch(`/hrms/config/${cfg.connector_id}/pause`).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['hrms-configs'] }),
  })

  const resumeMut = useMutation({
    mutationFn: () => api.patch(`/hrms/config/${cfg.connector_id}/resume`).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['hrms-configs'] }),
  })

  const testMut = useMutation({
    mutationFn: () => api.post(`/hrms/config/${cfg.connector_id}/test`).then(r => r.data),
    onSuccess:  (d) => setTestResult(d.ok),
    onError:    () => setTestResult(false),
  })

  const syncMut = useMutation({
    mutationFn: () => api.post(`/hrms/config/${cfg.connector_id}/sync`).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['hrms-configs', 'hrms-sync-log'] }),
  })

  const def = defs.find(d => d.connector_key === cfg.connector_key)

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-slate-800 text-sm">{cfg.display_name}</p>
          <p className="text-xs text-slate-400 font-mono">{cfg.connector_key} · {cfg.integration_mode}</p>
        </div>
        <StatusPill status={cfg.status} />
      </div>

      {/* Last sync */}
      {cfg.last_pulled_at && (
        <p className="text-xs text-slate-400">
          Last synced: {new Date(cfg.last_pulled_at).toLocaleString()}
        </p>
      )}

      {/* Auth method badge from definition */}
      {def && (
        <p className="text-xs text-slate-500">
          Auth: <span className="font-medium text-slate-700">{def.auth_method}</span>
        </p>
      )}

      {/* Test connection result */}
      {testResult !== null && (
        <div className={`flex items-center gap-1.5 text-xs rounded-lg px-3 py-2 ${
          testResult ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
        }`}>
          {testResult ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
          {testResult ? 'Connection successful' : 'Connection failed — check credentials'}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          onClick={() => testMut.mutate()}
          disabled={testMut.isPending}
          className="flex items-center gap-1 text-xs border border-slate-200 rounded-lg px-3 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {testMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <TestTube2 size={12} />}
          Test connection
        </button>

        {cfg.status === 'ACTIVE' ? (
          <>
            <button
              onClick={() => syncMut.mutate()}
              disabled={syncMut.isPending}
              className="flex items-center gap-1 text-xs bg-indigo-600 text-white rounded-lg px-3 py-1.5 hover:bg-indigo-700 disabled:opacity-50"
            >
              {syncMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Sync now
            </button>
            <button
              onClick={() => pauseMut.mutate()}
              disabled={pauseMut.isPending}
              className="flex items-center gap-1 text-xs border border-amber-200 rounded-lg px-3 py-1.5 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
            >
              <Pause size={12} />
              Pause
            </button>
          </>
        ) : cfg.status === 'PAUSED' ? (
          <button
            onClick={() => resumeMut.mutate()}
            disabled={resumeMut.isPending}
            className="flex items-center gap-1 text-xs bg-emerald-600 text-white rounded-lg px-3 py-1.5 hover:bg-emerald-700 disabled:opacity-50"
          >
            <Play size={12} />
            Resume
          </button>
        ) : null}

        <button
          onClick={() => setShowHistory(v => !v)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 ml-auto"
        >
          Sync history <ChevronDown size={12} className={showHistory ? 'rotate-180' : ''} />
        </button>
      </div>

      {showHistory && (
        <div className="pt-2 border-t border-slate-100">
          <SyncHistory connectorId={cfg.connector_id} />
        </div>
      )}
    </div>
  )
}

function AddConnectorForm({ defs, onClose }: { defs: ConnectorDef[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    connector_definition_id: '',
    display_name:            '',
    integration_mode:        'PULL',
    credentials:             '{}',
    pull_schedule:           '0 */6 * * *',
  })

  const createMut = useMutation({
    mutationFn: () => api.post('/hrms/config', {
      ...form,
      credentials: JSON.parse(form.credentials),
    }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hrms-configs'] })
      onClose()
    },
  })

  const selectedDef = defs.find(d => d.connector_definition_id === form.connector_definition_id)

  return (
    <div className="bg-white rounded-xl border border-indigo-100 shadow-sm p-6 space-y-4">
      <h2 className="font-semibold text-slate-800 text-sm">Connect an HRMS</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">HRMS System</label>
          <select
            value={form.connector_definition_id}
            onChange={e => {
              const def = defs.find(d => d.connector_definition_id === e.target.value)
              setForm(f => ({
                ...f,
                connector_definition_id: e.target.value,
                display_name: def?.display_name ?? '',
                integration_mode: def?.supported_modes[0] ?? 'PULL',
              }))
            }}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="">Select HRMS…</option>
            {defs.map(d => (
              <option key={d.connector_definition_id} value={d.connector_definition_id}>
                {d.display_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Display name</label>
          <input
            value={form.display_name}
            onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
            placeholder="e.g. Acme Darwinbox"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>

        {selectedDef && selectedDef.supported_modes.length > 1 && (
          <div>
            <label className="block text-xs text-slate-500 mb-1">Integration mode</label>
            <select
              value={form.integration_mode}
              onChange={e => setForm(f => ({ ...f, integration_mode: e.target.value }))}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {selectedDef.supported_modes.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        )}

        {form.integration_mode === 'PULL' && (
          <div>
            <label className="block text-xs text-slate-500 mb-1">Pull schedule (cron)</label>
            <input
              value={form.pull_schedule}
              onChange={e => setForm(f => ({ ...f, pull_schedule: e.target.value }))}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <p className="text-xs text-slate-400 mt-0.5">Default: every 6 hours</p>
          </div>
        )}
      </div>

      <div>
        <label className="block text-xs text-slate-500 mb-1">
          Credentials (JSON) — encrypted with your tenant KEK before storage
        </label>
        <textarea
          value={form.credentials}
          onChange={e => setForm(f => ({ ...f, credentials: e.target.value }))}
          rows={4}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          placeholder={selectedDef?.auth_method === 'OAUTH2'
            ? '{"client_id":"...","client_secret":"...","base_url":"https://..."}'
            : '{"api_key":"...","base_url":"https://..."}'}
        />
        <p className="text-xs text-slate-400 mt-0.5">
          Never stored in plaintext — KMS-encrypted at write time.
        </p>
      </div>

      {createMut.isError && (
        <p className="text-xs text-red-600">Failed to save. Check credentials JSON and try again.</p>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <button
          onClick={onClose}
          className="text-xs border border-slate-200 rounded-lg px-4 py-2 text-slate-600 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          onClick={() => createMut.mutate()}
          disabled={!form.connector_definition_id || !form.display_name || createMut.isPending}
          className="flex items-center gap-1 text-xs bg-indigo-600 text-white rounded-lg px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
        >
          {createMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plug size={12} />}
          Save connector
        </button>
      </div>
    </div>
  )
}

export function HRMSSettings() {
  const [showForm, setShowForm] = useState(false)

  const { data: configData, isLoading: configLoading, isError: configError } = useQuery<{ items: ConnectorConfig[] }>({
    queryKey:  ['hrms-configs'],
    queryFn:   () => api.get('/hrms/config').then(r => r.data),
    staleTime: 30_000,
  })

  const { data: defData } = useQuery<{ items: ConnectorDef[] }>({
    queryKey:  ['hrms-definitions-oa'],
    queryFn:   () => api.get('/admin/hrms/definitions').then(r => r.data),
    staleTime: 120_000,
  })

  const configs = configData?.items ?? []
  const defs    = defData?.items ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">HRMS Integration</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Connect your HRMS to automatically sync employee records
          </p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 text-xs bg-indigo-600 text-white rounded-lg px-3 py-2 hover:bg-indigo-700"
        >
          <Plug size={13} />
          Add connector
        </button>
      </div>

      {showForm && (
        <AddConnectorForm defs={defs} onClose={() => setShowForm(false)} />
      )}

      {configLoading && (
        <div className="flex items-center justify-center h-36 text-slate-400">
          <Loader2 className="animate-spin mr-2" size={18} />
          Loading connectors…
        </div>
      )}

      {configError && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 rounded-xl p-4">
          <AlertCircle size={16} />
          Failed to load HRMS configuration.
        </div>
      )}

      {!configLoading && !configError && configs.length === 0 && !showForm && (
        <div className="text-center py-16 text-slate-400">
          <Plug size={32} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm font-medium text-slate-600">No HRMS connected yet</p>
          <p className="text-xs mt-1">Click "Add connector" to sync employee records automatically.</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {configs.map(cfg => (
          <ConnectorCard key={cfg.connector_id} cfg={cfg} defs={defs} />
        ))}
      </div>
    </div>
  )
}
