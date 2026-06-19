import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

const SEVERITIES = ['ALL', 'P0', 'P1', 'P2', 'P3']
const STATUSES   = ['OPEN', 'INVESTIGATING', 'RESOLVED', 'FALSE_POSITIVE']

const SEV_STYLE: Record<string, string> = {
  P0: 'bg-red-100 text-red-700',
  P1: 'bg-orange-100 text-orange-700',
  P2: 'bg-amber-100 text-amber-700',
  P3: 'bg-slate-100 text-slate-600',
}
const STATUS_STYLE: Record<string, string> = {
  OPEN:          'bg-red-50 text-red-700',
  INVESTIGATING: 'bg-amber-50 text-amber-700',
  RESOLVED:      'bg-emerald-50 text-emerald-700',
  FALSE_POSITIVE:'bg-slate-100 text-slate-500',
}

export function AnomalyQueue() {
  const qc = useQueryClient()
  const [severity, setSeverity]       = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('OPEN')
  const [page, setPage] = useState(0)
  const PAGE = 50

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-anomaly-queue', severity, statusFilter, page],
    queryFn: () => api.get('/v1/ciso/anomaly-queue', {
      params: {
        severity:      severity !== 'ALL' ? severity : undefined,
        status_filter: statusFilter || undefined,
        offset: page * PAGE, limit: PAGE,
      },
    }).then(r => r.data),
    refetchInterval: 30_000,
  })

  const triageMut = useMutation({
    mutationFn: ({ anomaly_id, status }: { anomaly_id: string; status: string }) =>
      api.patch(`/v1/ciso/anomaly-queue/${anomaly_id}`, { status }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-anomaly-queue'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Anomaly Triage Queue</h1>
          <p className="text-sm text-slate-500 mt-0.5">Automated security detections. Triage each to INVESTIGATING, RESOLVED, or FALSE_POSITIVE.</p>
        </div>
        <span className="text-xs font-mono text-slate-400">{data?.total ?? 0} matching</span>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex gap-1">
          {SEVERITIES.map(s => (
            <button key={s} onClick={() => { setSeverity(s); setPage(0) }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      severity === s
                        ? 'bg-slate-800 text-white border-slate-800'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}>{s}</button>
          ))}
        </div>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(0) }}
                className="border border-slate-200 rounded-lg px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-red-400">
          {STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
        </select>
      </div>

      {isLoading && (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">Failed to load anomaly queue.</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">Retry</button>
        </div>
      )}

      {!isLoading && !isError && data?.items?.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-16 text-center">
          <CheckCircle size={32} className="text-emerald-400 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">Queue clear</p>
          <p className="text-xs text-slate-400 mt-1">No anomalies matching the current filter.</p>
        </div>
      )}

      <div className="space-y-3">
        {data?.items?.map((row: any) => (
          <div key={row.anomaly_id}
               className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 flex items-start gap-4">
            <ShieldAlert size={20} className={
              row.severity === 'P0' ? 'text-red-500 shrink-0 mt-0.5' :
              row.severity === 'P1' ? 'text-orange-500 shrink-0 mt-0.5' :
              'text-amber-500 shrink-0 mt-0.5'
            } />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-slate-800">{row.rule_name?.replace(/_/g, ' ')}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEV_STYLE[row.severity] ?? 'bg-slate-100 text-slate-600'}`}>
                  {row.severity}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[row.status] ?? 'bg-slate-100 text-slate-600'}`}>
                  {row.status?.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Detected {fmtDateTime(row.detected_at)}
                {row.acknowledged_at ? ` · Acknowledged ${fmtDateTime(row.acknowledged_at)}` : ''}
              </p>
              {row.financial_pattern && (
                <p className="text-xs text-slate-500 mt-0.5">Pattern: {row.financial_pattern}</p>
              )}
            </div>
            {row.status === 'OPEN' || row.status === 'INVESTIGATING' ? (
              <div className="flex flex-col gap-1.5 shrink-0">
                {row.status === 'OPEN' && (
                  <button onClick={() => triageMut.mutate({ anomaly_id: row.anomaly_id, status: 'INVESTIGATING' })}
                          disabled={triageMut.isPending}
                          className="text-xs font-medium text-amber-700 border border-amber-200 px-3 py-1.5 rounded-lg hover:bg-amber-50">
                    Investigate
                  </button>
                )}
                <button onClick={() => triageMut.mutate({ anomaly_id: row.anomaly_id, status: 'RESOLVED' })}
                        disabled={triageMut.isPending}
                        className="text-xs font-medium text-emerald-700 border border-emerald-200 px-3 py-1.5 rounded-lg hover:bg-emerald-50">
                  Resolve
                </button>
                <button onClick={() => triageMut.mutate({ anomaly_id: row.anomaly_id, status: 'FALSE_POSITIVE' })}
                        disabled={triageMut.isPending}
                        className="text-xs font-medium text-slate-500 border border-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-50">
                  False positive
                </button>
              </div>
            ) : (
              <CheckCircle size={16} className="text-emerald-400 shrink-0 mt-1" />
            )}
          </div>
        ))}
      </div>

      {(data?.total ?? 0) > PAGE && (
        <div className="flex justify-between items-center text-sm">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  className="px-4 py-2 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">
            Previous
          </button>
          <span className="text-slate-400 text-xs">Page {page + 1} of {Math.ceil((data?.total ?? 0) / PAGE)}</span>
          <button onClick={() => setPage(p => p + 1)}
                  disabled={(page + 1) * PAGE >= (data?.total ?? 0)}
                  className="px-4 py-2 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">
            Next
          </button>
        </div>
      )}
    </div>
  )
}
