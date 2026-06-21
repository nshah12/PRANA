/**
 * SecurityIncidents — CISO view of auto-generated security incident tickets.
 * Backed by POST-017 `incident` table. Different from PA's service_incident table.
 * CISO can resolve or escalate; all scoped to their tenant_id from JWT.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert, CheckCircle, TrendingUp, Clock, Filter } from 'lucide-react'
import { api } from '@/lib/api'

const SEV: Record<string, { pill: string; ring: string }> = {
  P0: { pill: 'bg-red-100 text-red-700 border border-red-300',    ring: 'border-red-300' },
  P1: { pill: 'bg-orange-100 text-orange-700 border border-orange-300', ring: 'border-orange-200' },
  P2: { pill: 'bg-amber-100 text-amber-700 border border-amber-200',   ring: 'border-amber-200' },
  P3: { pill: 'bg-slate-100 text-slate-600 border border-slate-200',   ring: 'border-slate-200' },
}

const STATUS_STYLE: Record<string, string> = {
  OPEN:       'bg-red-50 text-red-700',
  IN_PROGRESS:'bg-amber-50 text-amber-700',
  ESCALATED:  'bg-orange-50 text-orange-700',
  RESOLVED:   'bg-emerald-50 text-emerald-700',
}

function SlaChip({ deadline }: { deadline: string | null }) {
  if (!deadline) return null
  const ms = new Date(deadline).getTime() - Date.now()
  const hrs = Math.round(ms / 36e5)
  const overdue = ms < 0
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${overdue ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}>
      {overdue ? `${Math.abs(hrs)}h overdue` : `SLA ${hrs}h left`}
    </span>
  )
}

export function SecurityIncidents() {
  const qc = useQueryClient()
  const [severity, setSeverity] = useState('')
  const [status, setStatus]     = useState('')
  const [resolveId, setResolveId] = useState<string | null>(null)
  const [resolveNote, setResolveNote] = useState('')

  const params = new URLSearchParams()
  if (severity) params.set('severity', severity)
  if (status)   params.set('status', status)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-incidents', severity, status],
    queryFn:  () => api.get(`/v1/ciso/incidents?${params}`).then(r => r.data),
  })

  const resolve = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      api.patch(`/v1/ciso/incidents/${id}/resolve`, { resolution_note: note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ciso-incidents'] })
      setResolveId(null)
      setResolveNote('')
    },
  })

  const escalate = useMutation({
    mutationFn: (id: string) => api.patch(`/v1/ciso/incidents/${id}/escalate`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-incidents'] }),
  })

  const incidents: any[] = data?.items ?? []

  const p0Open = incidents.filter(i => i.severity === 'P0' && i.status !== 'RESOLVED').length
  const p1Open = incidents.filter(i => i.severity === 'P1' && i.status !== 'RESOLVED').length
  const totalOpen = incidents.filter(i => i.status === 'OPEN').length

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
            <ShieldAlert size={20} className="text-red-500" />
            Security Incidents
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Auto-created for P0/P1 anomalies · Resolve or escalate within SLA
          </p>
        </div>
        <button onClick={() => refetch()}
          className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50">
          Refresh
        </button>
      </div>

      {/* Summary chips */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`rounded-xl p-4 border ${p0Open ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">P0 Open</p>
          <p className={`text-3xl font-bold mt-1 ${p0Open ? 'text-red-600' : 'text-slate-800'}`}>{p0Open}</p>
          <p className="text-xs text-slate-400 mt-1">SLA: 30 min</p>
        </div>
        <div className={`rounded-xl p-4 border ${p1Open ? 'bg-orange-50 border-orange-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">P1 Open</p>
          <p className={`text-3xl font-bold mt-1 ${p1Open ? 'text-orange-600' : 'text-slate-800'}`}>{p1Open}</p>
          <p className="text-xs text-slate-400 mt-1">SLA: 4 hrs</p>
        </div>
        <div className="rounded-xl p-4 border bg-white border-slate-200">
          <p className="text-xs text-slate-500 uppercase tracking-wide">Total Open</p>
          <p className="text-3xl font-bold mt-1 text-slate-800">{totalOpen}</p>
          <p className="text-xs text-slate-400 mt-1">All severities</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Filter size={14} className="text-slate-400" />
        <select value={severity} onChange={e => setSeverity(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">All severities</option>
          {['P0','P1','P2','P3'].map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={status} onChange={e => setStatus(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">All statuses</option>
          {['OPEN','IN_PROGRESS','ESCALATED','RESOLVED'].map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">Failed to load incidents.</p>
          <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
        </div>
      ) : incidents.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">No incidents match this filter</p>
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
                      <span className="text-xs text-slate-400 font-mono">{inc.incident_type}</span>
                      <SlaChip deadline={inc.sla_deadline} />
                    </div>
                    <p className="font-medium text-slate-800">{inc.title}</p>
                    {inc.description && (
                      <p className="text-xs text-slate-500">{inc.description}</p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <Clock size={10} /> Created {new Date(inc.created_at).toLocaleString('en-IN')}
                      </span>
                      {inc.resolved_at && (
                        <span className="text-emerald-600">
                          ✓ Resolved {new Date(inc.resolved_at).toLocaleString('en-IN')}
                        </span>
                      )}
                      {inc.escalated_at && (
                        <span className="text-orange-600">
                          ↑ Escalated {new Date(inc.escalated_at).toLocaleString('en-IN')}
                        </span>
                      )}
                    </div>
                    {inc.resolution_note && (
                      <p className="text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-1">
                        ✓ {inc.resolution_note}
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
                            placeholder="Resolution note…"
                            rows={2}
                            className="text-xs w-48 border border-slate-200 rounded-lg px-2 py-1.5 resize-none"
                          />
                          <div className="flex gap-1.5">
                            <button
                              onClick={() => resolve.mutate({ id: inc.incident_id, note: resolveNote })}
                              disabled={!resolveNote || resolve.isPending}
                              className="flex-1 text-xs px-2 py-1 bg-emerald-600 text-white rounded-lg
                                         hover:bg-emerald-700 disabled:opacity-50">
                              {resolve.isPending ? '…' : 'Confirm'}
                            </button>
                            <button
                              onClick={() => { setResolveId(null); setResolveNote('') }}
                              className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500">
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => setResolveId(inc.incident_id)}
                            className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center gap-1">
                            <CheckCircle size={11} /> Resolve
                          </button>
                          {inc.status !== 'ESCALATED' && (
                            <button
                              onClick={() => escalate.mutate(inc.incident_id)}
                              disabled={escalate.isPending}
                              className="text-xs px-3 py-1.5 border border-orange-300 text-orange-700 rounded-lg hover:bg-orange-50 flex items-center gap-1 disabled:opacity-50">
                              <TrendingUp size={11} /> Escalate
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
    </div>
  )
}
