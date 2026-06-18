import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Zap, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

const SEVERITY_COLORS: Record<string, string> = {
  HIGH:   'bg-red-50 text-red-700',
  MEDIUM: 'bg-amber-50 text-amber-700',
  LOW:    'bg-slate-100 text-slate-600',
}

export function AnomalyDetection() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['pa-anomalies'],
    queryFn: () => api.get('/admin/anomalies').then(r => r.data),
    refetchInterval: 60_000,
  })

  const ackMut = useMutation({
    mutationFn: (id: string) => api.post(`/admin/anomalies/${id}/acknowledge`, {}).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-anomalies'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Anomaly Detection</h1>
        <span className="text-xs font-mono text-slate-400">Platform Admin · refreshes every 60s</span>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Unacknowledged', value: data?.unacknowledged ?? 0, color: 'text-red-600' },
          { label: 'High severity',  value: data?.high_severity ?? 0,  color: 'text-amber-600' },
          { label: 'Resolved (7d)',  value: data?.resolved_7d ?? 0,    color: 'text-emerald-600' },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Zap size={14} className="text-amber-500" />
          <h2 className="font-medium text-slate-800">Active anomalies</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.anomalies ?? []).map((a: any) => (
            <div key={a.anomaly_id} className="px-5 py-4 flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-700">{a.anomaly_type?.replace(/_/g, ' ')}</span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${SEVERITY_COLORS[a.severity] ?? 'bg-slate-100 text-slate-600'}`}>
                    {a.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{a.description}</p>
                <p className="text-xs text-slate-400 mt-1 font-mono">{a.tenant_name} · {fmtDateTime(a.detected_at)}</p>
              </div>
              {!a.acknowledged_at && (
                <button
                  onClick={() => ackMut.mutate(a.anomaly_id)}
                  disabled={ackMut.isPending}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium shrink-0"
                >
                  Acknowledge
                </button>
              )}
              {a.acknowledged_at && (
                <CheckCircle size={16} className="text-emerald-500 shrink-0 mt-0.5" />
              )}
            </div>
          ))}
          {!data?.anomalies?.length && (
            <div className="px-5 py-10 flex flex-col items-center gap-2 text-slate-400">
              <CheckCircle size={28} className="text-emerald-300" />
              <p className="text-sm">No active anomalies.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
