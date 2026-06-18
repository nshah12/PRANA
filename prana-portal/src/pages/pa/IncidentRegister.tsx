import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, RefreshCw, ShieldAlert } from 'lucide-react'
import { api } from '@/lib/api'

const SEVERITY_STYLE: Record<string, string> = {
  P1: 'bg-red-100 text-red-700 border border-red-200',
  P2: 'bg-amber-100 text-amber-700 border border-amber-200',
  P3: 'bg-slate-100 text-slate-600 border border-slate-200',
}

const STATUS_STYLE: Record<string, string> = {
  OPEN:         'bg-red-50 text-red-700',
  ACKNOWLEDGED: 'bg-amber-50 text-amber-700',
  RESOLVED:     'bg-emerald-50 text-emerald-700',
}

const SERVICE_ICON: Record<string, string> = {
  'prana-api':  '⚙️',
  'prana-ai':   '🤖',
  'prana-ask':  '💬',
  'kafka':      '📨',
  'redis':      '⚡',
  'db':         '🗄️',
}

export function IncidentRegister() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['pa-incidents'],
    queryFn: () => api.get('/pa/incidents').then(r => r.data),
    refetchInterval: 60_000,   // auto-refresh every 60s
  })

  const triggerCheck = useMutation({
    mutationFn: () => api.post('/pa/incidents/run-check', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-incidents'] }),
  })

  const acknowledge = useMutation({
    mutationFn: (id: string) => api.post(`/pa/incidents/${id}/acknowledge`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-incidents'] }),
  })

  const resolve = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      api.post(`/pa/incidents/${id}/resolve`, { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-incidents'] }),
  })

  const incidents: any[] = data?.incidents ?? []
  const openCount: number = data?.open_count ?? 0
  const p1Open: number = data?.p1_open ?? 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
            <ShieldAlert size={20} className="text-red-500" />
            Service Incidents
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Auto-detected by SystemHealthWorkflow · polls every 2 min
          </p>
        </div>
        <button
          onClick={() => triggerCheck.mutate()}
          disabled={triggerCheck.isPending}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={14} className={triggerCheck.isPending ? 'animate-spin' : ''} />
          Run check now
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`rounded-xl p-4 border ${p1Open > 0 ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">P1 Open</p>
          <p className={`text-3xl font-bold mt-1 ${p1Open > 0 ? 'text-red-600' : 'text-slate-800'}`}>{p1Open}</p>
          <p className="text-xs text-slate-400 mt-1">Critical — auth / data</p>
        </div>
        <div className={`rounded-xl p-4 border ${openCount > 0 ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
          <p className="text-xs text-slate-500 uppercase tracking-wide">Total Open</p>
          <p className={`text-3xl font-bold mt-1 ${openCount > 0 ? 'text-amber-600' : 'text-slate-800'}`}>{openCount}</p>
          <p className="text-xs text-slate-400 mt-1">Across all services</p>
        </div>
        <div className="rounded-xl p-4 border bg-white border-slate-200">
          <p className="text-xs text-slate-500 uppercase tracking-wide">All Incidents</p>
          <p className="text-3xl font-bold mt-1 text-slate-800">{incidents.length}</p>
          <p className="text-xs text-slate-400 mt-1">Last 100 records</p>
        </div>
      </div>

      {/* Incident list */}
      {isLoading ? (
        <div className="text-sm text-slate-400 py-8 text-center">Loading incidents…</div>
      ) : incidents.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">All systems healthy</p>
          <p className="text-sm mt-1">No incidents detected</p>
        </div>
      ) : (
        <div className="space-y-3">
          {incidents.map((inc: any) => (
            <div key={inc.incident_id}
              className={`bg-white border rounded-xl p-4 ${inc.status === 'OPEN' ? 'border-red-200' : 'border-slate-200'}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <span className="text-xl shrink-0">{SERVICE_ICON[inc.service_name] ?? '🔧'}</span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SEVERITY_STYLE[inc.severity]}`}>
                        {inc.severity}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[inc.status]}`}>
                        {inc.status}
                      </span>
                      <span className="text-xs text-slate-400 font-mono">{inc.service_name}</span>
                    </div>
                    <p className="font-medium text-slate-800 mt-1">{inc.title}</p>
                    {inc.detail && (
                      <p className="text-xs text-slate-500 font-mono mt-0.5 truncate">{inc.detail}</p>
                    )}
                    <p className="text-xs text-slate-400 mt-1">
                      Detected {new Date(inc.detected_at).toLocaleString('en-IN')}
                      {inc.resolved_at && ` · Resolved ${new Date(inc.resolved_at).toLocaleString('en-IN')}`}
                    </p>
                    {inc.resolution_note && (
                      <p className="text-xs text-emerald-600 mt-1">✓ {inc.resolution_note}</p>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {inc.status === 'OPEN' && (
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => acknowledge.mutate(inc.incident_id)}
                      className="text-xs px-3 py-1.5 border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50"
                    >
                      Acknowledge
                    </button>
                    <button
                      onClick={() => resolve.mutate({ id: inc.incident_id, note: 'Manually resolved by PA' })}
                      className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                    >
                      Resolve
                    </button>
                  </div>
                )}
                {inc.status === 'ACKNOWLEDGED' && (
                  <button
                    onClick={() => resolve.mutate({ id: inc.incident_id, note: 'Manually resolved by PA' })}
                    className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shrink-0"
                  >
                    Resolve
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
