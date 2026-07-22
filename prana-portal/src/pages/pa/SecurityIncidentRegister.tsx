/**
 * SecurityIncidentRegister — PA cross-tenant view of security anomaly incidents.
 * Backed by migration-017 `incident` table (security + DPDP + SLA breach).
 * Separate from IncidentRegister.tsx which handles `service_incident` (platform health).
 * PA can filter by tenant, severity, status and resolve / escalate any incident.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert, CheckCircle, TrendingUp, Clock, Filter, Globe, Bug, XCircle, ArrowUpCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const SEV: Record<string, { pill: string; ring: string }> = {
  P0: { pill: 'bg-red-100 text-red-700 border border-red-300',         ring: 'border-red-300' },
  P1: { pill: 'bg-orange-100 text-orange-700 border border-orange-300', ring: 'border-orange-200' },
  P2: { pill: 'bg-amber-100 text-amber-700 border border-amber-200',    ring: 'border-amber-200' },
  P3: { pill: 'bg-slate-100 text-slate-600 border border-slate-200',    ring: 'border-slate-200' },
}

const STATUS_STYLE: Record<string, string> = {
  OPEN:        'bg-red-50 text-red-700',
  IN_PROGRESS: 'bg-amber-50 text-amber-700',
  ESCALATED:   'bg-orange-50 text-orange-700',
  RESOLVED:    'bg-emerald-50 text-emerald-700',
}

function SlaChip({ deadline }: { deadline: string | null }) {
  if (!deadline) return null
  const ms = new Date(deadline).getTime() - Date.now()
  const hrs = Math.round(Math.abs(ms) / 36e5)
  const overdue = ms < 0
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${overdue ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}>
      {overdue ? `${hrs}h overdue` : `${hrs}h left`}
    </span>
  )
}

function ErrorsPanel() {
  const qc = useQueryClient()
  const [tenantId, setTenantId]     = useState('')
  const [errStatus, setErrStatus]   = useState('')
  const [resolveId, setResolveId]   = useState<string | null>(null)
  const [resolveNote, setResolveNote] = useState('')
  const [promoteId, setPromoteId]   = useState<string | null>(null)
  const [promoteSev, setPromoteSev] = useState('P2')

  const params = new URLSearchParams({ limit: '100' })
  if (tenantId) params.set('tenant_id', tenantId)
  if (errStatus) params.set('error_status', errStatus)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-errors', tenantId, errStatus],
    queryFn:  () => api.get(`/admin/errors?${params}`).then(r => r.data),
    refetchInterval: 60_000,
  })

  const acknowledge = useMutation({
    mutationFn: (id: string) => api.post(`/admin/errors/${id}/acknowledge`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-errors'] }),
  })

  const ignore = useMutation({
    mutationFn: (id: string) => api.post(`/admin/errors/${id}/ignore`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-errors'] }),
  })

  const resolve = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      api.post(`/admin/errors/${id}/resolve`, { resolution_note: note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-errors'] })
      setResolveId(null)
      setResolveNote('')
    },
  })

  const promote = useMutation({
    mutationFn: ({ id, severity }: { id: string; severity: string }) =>
      api.post(`/admin/errors/${id}/promote-to-incident`, { severity }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-errors'] })
      qc.invalidateQueries({ queryKey: ['pa-security-incidents'] })
      setPromoteId(null)
    },
  })

  const errors: any[] = data?.items ?? []
  const openCount = errors.filter(e => e.status === 'NEW' || e.status === 'ACKNOWLEDGED').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{tUi('ERR_SUB')}</p>
        <button onClick={() => refetch()}
          className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50">
          {tUi('CISO_NOTIF_LOG_REFRESH')}
        </button>
      </div>

      <div className={`rounded-xl p-4 border max-w-xs ${openCount > 0 ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
        <p className="text-xs text-slate-500 uppercase tracking-wide">{tUi('ERR_OPEN_TITLE')}</p>
        <p className={`text-3xl font-bold mt-1 ${openCount > 0 ? 'text-amber-600' : 'text-slate-800'}`}>{openCount}</p>
        <p className="text-xs text-slate-400 mt-1">{tUi('ERR_OPEN_NOTE')}</p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={14} className="text-slate-400" />
        <div className="flex items-center gap-1.5">
          <Globe size={12} className="text-slate-400" />
          <input
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
            placeholder={tUi('PA_SEC_INC_TENANT_FILTER_PLACEHOLDER')}
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 w-52 text-slate-600"
          />
        </div>
        <select value={errStatus} onChange={e => setErrStatus(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">{tUi('ERR_STATUS_FILTER_ALL')}</option>
          {['NEW','ACKNOWLEDGED','RESOLVED','IGNORED'].map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {/* Error list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">{tUi('ERR_LOAD_FAILED')}</p>
          <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">{tUi('CFO_ATTRITION_RETRY')}</button>
        </div>
      ) : errors.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">{tUi('ERR_EMPTY')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {errors.map((err: any) => (
            <div key={err.error_id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-mono">
                      {err.status}
                    </span>
                    <span className="text-xs font-mono text-slate-400">{err.source}</span>
                    {err.source_detail && (
                      <span className="text-xs font-mono text-slate-400">· {err.source_detail}</span>
                    )}
                  </div>
                  <p className="font-medium text-slate-800">{err.exception_type}</p>
                  <div className="flex items-center gap-4 text-xs text-slate-400 flex-wrap">
                    {err.tenant_id && (
                      <span className="font-mono">{tUi('PA_SEC_INC_TENANT_PREFIX')} {err.tenant_id.slice(0, 8)}…</span>
                    )}
                    <span>{tUi('ERR_OCCURRENCES_PREFIX')} {err.occurrence_count}{tUi('ERR_OCCURRENCES_SUFFIX')}</span>
                    <span className="flex items-center gap-1">
                      <Clock size={10} /> {tUi('ERR_LAST_SEEN_PREFIX')} {new Date(err.last_seen_at).toLocaleString('en-IN')}
                    </span>
                  </div>
                  {err.linked_incident_id && (
                    <p className="text-xs text-indigo-600">
                      {tUi('ERR_LINKED_INCIDENT_PREFIX')} {err.linked_incident_id.slice(0, 8)}…
                    </p>
                  )}
                </div>

                {/* Actions */}
                {(err.status === 'NEW' || err.status === 'ACKNOWLEDGED') && (
                  <div className="flex flex-col gap-2 shrink-0 items-end">
                    {resolveId === err.error_id ? (
                      <div className="space-y-2">
                        <textarea
                          value={resolveNote}
                          onChange={e => setResolveNote(e.target.value)}
                          placeholder={tUi('CISO_SEC_INC_RESOLUTION_PLACEHOLDER')}
                          rows={2}
                          className="text-xs w-48 border border-slate-200 rounded-lg px-2 py-1.5 resize-none"
                        />
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => resolve.mutate({ id: err.error_id, note: resolveNote })}
                            disabled={!resolveNote || resolve.isPending}
                            className="flex-1 text-xs px-2 py-1 bg-emerald-600 text-white rounded-lg
                                       hover:bg-emerald-700 disabled:opacity-50">
                            {resolve.isPending ? '…' : tUi('CISO_SEC_INC_CONFIRM')}
                          </button>
                          <button
                            onClick={() => { setResolveId(null); setResolveNote('') }}
                            className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500">
                            {tUi('CISO_SEC_INC_CANCEL')}
                          </button>
                        </div>
                      </div>
                    ) : promoteId === err.error_id ? (
                      <div className="space-y-2">
                        <select value={promoteSev} onChange={e => setPromoteSev(e.target.value)}
                          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white w-full">
                          {['P1','P2','P3'].map(s => <option key={s}>{s}</option>)}
                        </select>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => promote.mutate({ id: err.error_id, severity: promoteSev })}
                            disabled={promote.isPending}
                            className="flex-1 text-xs px-2 py-1 bg-indigo-600 text-white rounded-lg
                                       hover:bg-indigo-700 disabled:opacity-50">
                            {promote.isPending ? '…' : tUi('CISO_SEC_INC_CONFIRM')}
                          </button>
                          <button
                            onClick={() => setPromoteId(null)}
                            className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500">
                            {tUi('CISO_SEC_INC_CANCEL')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="flex gap-1.5">
                          {err.status === 'NEW' && (
                            <button
                              onClick={() => acknowledge.mutate(err.error_id)}
                              className="text-xs px-3 py-1.5 border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50">
                              {tUi('ERR_ACK_BTN')}
                            </button>
                          )}
                          <button
                            onClick={() => setResolveId(err.error_id)}
                            className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center gap-1">
                            <CheckCircle size={11} /> {tUi('ERR_RESOLVE_BTN')}
                          </button>
                        </div>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => ignore.mutate(err.error_id)}
                            disabled={ignore.isPending}
                            className="text-xs px-3 py-1.5 border border-slate-200 text-slate-500 rounded-lg hover:bg-slate-50 flex items-center gap-1 disabled:opacity-50">
                            <XCircle size={11} /> {tUi('ERR_IGNORE_BTN')}
                          </button>
                          <button
                            onClick={() => setPromoteId(err.error_id)}
                            className="text-xs px-3 py-1.5 border border-indigo-300 text-indigo-700 rounded-lg hover:bg-indigo-50 flex items-center gap-1">
                            <ArrowUpCircle size={11} /> {tUi('ERR_PROMOTE_BTN')}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SecurityIncidentRegister() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'incidents' | 'errors'>('incidents')
  const [tenantId, setTenantId]   = useState('')
  const [severity, setSeverity]   = useState('')
  const [incStatus, setIncStatus] = useState('')
  const [resolveId, setResolveId] = useState<string | null>(null)
  const [resolveNote, setResolveNote] = useState('')

  const params = new URLSearchParams({ limit: '100' })
  if (tenantId) params.set('tenant_id', tenantId)
  if (severity) params.set('severity', severity)
  if (incStatus) params.set('incident_status', incStatus)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-security-incidents', tenantId, severity, incStatus],
    queryFn:  () => api.get(`/admin/security-incidents?${params}`).then(r => r.data),
    refetchInterval: 60_000,
    enabled: tab === 'incidents',
  })

  const resolve = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      api.patch(`/admin/security-incidents/${id}/resolve`, { resolution_note: note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-security-incidents'] })
      setResolveId(null)
      setResolveNote('')
    },
  })

  const escalate = useMutation({
    mutationFn: (id: string) => api.patch(`/admin/security-incidents/${id}/escalate`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-security-incidents'] }),
  })

  const incidents: any[] = data?.items ?? []
  const p0Open = incidents.filter(i => i.severity === 'P0' && i.status !== 'RESOLVED').length
  const p1Open = incidents.filter(i => i.severity === 'P1' && i.status !== 'RESOLVED').length
  const totalOpen = incidents.filter(i => i.status === 'OPEN').length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
            <ShieldAlert size={20} className="text-red-500" />
            {tUi('PA_SEC_INC_TITLE')}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {tUi('PA_SEC_INC_SUB')}
          </p>
        </div>
        {tab === 'incidents' && (
          <button onClick={() => refetch()}
            className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50">
            {tUi('CISO_NOTIF_LOG_REFRESH')}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab('incidents')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'incidents' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <ShieldAlert size={14} /> {tUi('ERR_TAB_INCIDENTS')}
        </button>
        <button
          onClick={() => setTab('errors')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'errors' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <Bug size={14} /> {tUi('ERR_TAB_ERRORS')}
        </button>
      </div>

      {tab === 'errors' ? <ErrorsPanel /> : (
      <>
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`rounded-xl p-4 border ${p0Open ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">{tUi('CISO_SEC_INC_P0_OPEN')}</p>
          <p className={`text-3xl font-bold mt-1 ${p0Open ? 'text-red-600' : 'text-slate-800'}`}>{p0Open}</p>
          <p className="text-xs text-slate-400 mt-1">{tUi('PA_SEC_INC_P0_SLA')}</p>
        </div>
        <div className={`rounded-xl p-4 border ${p1Open ? 'bg-orange-50 border-orange-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">{tUi('CISO_SEC_INC_P1_OPEN')}</p>
          <p className={`text-3xl font-bold mt-1 ${p1Open ? 'text-orange-600' : 'text-slate-800'}`}>{p1Open}</p>
          <p className="text-xs text-slate-400 mt-1">{tUi('PA_SEC_INC_P1_SLA')}</p>
        </div>
        <div className="rounded-xl p-4 border bg-white border-slate-200">
          <p className="text-xs text-slate-500 uppercase tracking-wide">{tUi('CISO_SEC_INC_TOTAL_OPEN')}</p>
          <p className="text-3xl font-bold mt-1 text-slate-800">{totalOpen}</p>
          <p className="text-xs text-slate-400 mt-1">{tUi('PA_SEC_INC_TOTAL_NOTE')}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={14} className="text-slate-400" />
        <div className="flex items-center gap-1.5">
          <Globe size={12} className="text-slate-400" />
          <input
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
            placeholder={tUi('PA_SEC_INC_TENANT_FILTER_PLACEHOLDER')}
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 w-52 text-slate-600"
          />
        </div>
        <select value={severity} onChange={e => setSeverity(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">{tUi('CISO_SEC_INC_ALL_SEV_NOTE')}</option>
          {['P0','P1','P2','P3'].map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={incStatus} onChange={e => setIncStatus(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">{tUi('CISO_SEC_INC_ALL_STATUSES')}</option>
          {['OPEN','IN_PROGRESS','ESCALATED','RESOLVED'].map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {/* Incident list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">{tUi('PA_SEC_INC_LOAD_FAILED')}</p>
          <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">{tUi('CFO_ATTRITION_RETRY')}</button>
        </div>
      ) : incidents.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">{tUi('PA_SEC_INC_NONE')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {incidents.map((inc: any) => {
            const sev = SEV[inc.severity] ?? SEV.P3
            return (
              <div key={inc.incident_id}
                className={`bg-white border rounded-xl p-4 ${sev.ring}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${sev.pill}`}>
                        {inc.severity}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[inc.status] ?? ''}`}>
                        {inc.status}
                      </span>
                      <span className="text-xs font-mono text-slate-400">{inc.incident_type}</span>
                      <SlaChip deadline={inc.sla_deadline} />
                    </div>
                    <p className="font-medium text-slate-800">{inc.title}</p>
                    {inc.description && (
                      <p className="text-xs text-slate-500">{inc.description}</p>
                    )}
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      {inc.tenant_id && (
                        <span className="font-mono">{tUi('PA_SEC_INC_TENANT_PREFIX')} {inc.tenant_id.slice(0, 8)}…</span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock size={10} /> {new Date(inc.created_at).toLocaleString('en-IN')}
                      </span>
                      {inc.assigned_role && (
                        <span>{tUi('PA_SEC_INC_ASSIGNED_PREFIX')} {inc.assigned_role}</span>
                      )}
                    </div>
                    {inc.resolution_note && (
                      <p className="text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-1">
                        ✓ {inc.resolution_note}
                      </p>
                    )}
                    {inc.escalated_at && (
                      <p className="text-xs text-orange-600">
                        ↑ {tUi('CISO_SEC_INC_ESCALATED_PREFIX')} {new Date(inc.escalated_at).toLocaleString('en-IN')}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  {inc.status !== 'RESOLVED' && (
                    <div className="flex flex-col gap-2 shrink-0">
                      {resolveId === inc.incident_id ? (
                        <div className="space-y-2">
                          <textarea
                            value={resolveNote}
                            onChange={e => setResolveNote(e.target.value)}
                            placeholder={tUi('CISO_SEC_INC_RESOLUTION_PLACEHOLDER')}
                            rows={2}
                            className="text-xs w-48 border border-slate-200 rounded-lg px-2 py-1.5 resize-none"
                          />
                          <div className="flex gap-1.5">
                            <button
                              onClick={() => resolve.mutate({ id: inc.incident_id, note: resolveNote })}
                              disabled={!resolveNote || resolve.isPending}
                              className="flex-1 text-xs px-2 py-1 bg-emerald-600 text-white rounded-lg
                                         hover:bg-emerald-700 disabled:opacity-50">
                              {resolve.isPending ? '…' : tUi('CISO_SEC_INC_CONFIRM')}
                            </button>
                            <button
                              onClick={() => { setResolveId(null); setResolveNote('') }}
                              className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500">
                              {tUi('CISO_SEC_INC_CANCEL')}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => setResolveId(inc.incident_id)}
                            className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center gap-1">
                            <CheckCircle size={11} /> {tUi('CISO_SEC_INC_RESOLVE')}
                          </button>
                          {inc.status !== 'ESCALATED' && (
                            <button
                              onClick={() => escalate.mutate(inc.incident_id)}
                              disabled={escalate.isPending}
                              className="text-xs px-3 py-1.5 border border-orange-300 text-orange-700 rounded-lg hover:bg-orange-50 flex items-center gap-1 disabled:opacity-50">
                              <TrendingUp size={11} /> {tUi('CISO_SEC_INC_ESCALATE')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
      </>
      )}
    </div>
  )
}
