import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Clock, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

const STATUS_COLORS: Record<string, string> = {
  OPEN:        'bg-red-50 text-red-700',
  IN_PROGRESS: 'bg-amber-50 text-amber-700',
  RESOLVED:    'bg-emerald-50 text-emerald-700',
  ESCALATED:   'bg-purple-50 text-purple-700',
}

export function ExceptionOverview() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['pa-exceptions'],
    queryFn: () => api.get('/admin/exceptions').then(r => r.data),
    refetchInterval: 30_000,
  })

  const resolveMut = useMutation({
    mutationFn: (id: string) => api.post(`/admin/exceptions/${id}/resolve`, {}).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-exceptions'] }),
  })

  const stats = [
    { label: 'Open',        value: data?.open_count ?? 0,       color: 'text-red-600' },
    { label: 'In progress', value: data?.in_progress_count ?? 0, color: 'text-amber-600' },
    { label: 'Resolved 24h',value: data?.resolved_24h ?? 0,     color: 'text-emerald-600' },
    { label: 'SLA breach',  value: data?.sla_breach_count ?? 0, color: 'text-purple-600' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Exception Overview</h1>
        <span className="text-xs font-mono text-slate-400">Platform Admin · refreshes every 30s</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <AlertCircle size={14} className="text-red-500" />
          <h2 className="font-medium text-slate-800">Active exceptions</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.exceptions ?? []).map((ex: any) => (
            <div key={ex.exception_id} className="px-5 py-4 flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-700 truncate">{ex.document_name}</span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_COLORS[ex.status] ?? 'bg-slate-100 text-slate-600'}`}>
                    {ex.status}
                  </span>
                  {ex.sla_breached && (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-50 text-purple-700">SLA breach</span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">{ex.tenant_name} · {ex.exception_type?.replace(/_/g, ' ')}</p>
                <div className="flex items-center gap-1 mt-1 text-xs text-slate-400">
                  <Clock size={11} />
                  <span>{fmtDateTime(ex.created_at)}</span>
                </div>
              </div>
              {ex.status !== 'RESOLVED' && (
                <button
                  onClick={() => resolveMut.mutate(ex.exception_id)}
                  disabled={resolveMut.isPending}
                  className="text-xs text-emerald-600 hover:text-emerald-800 font-medium shrink-0"
                >
                  Mark resolved
                </button>
              )}
            </div>
          ))}
          {!data?.exceptions?.length && (
            <div className="px-5 py-10 flex flex-col items-center gap-2 text-slate-400">
              <CheckCircle size={28} className="text-emerald-300" />
              <p className="text-sm">No active exceptions.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
