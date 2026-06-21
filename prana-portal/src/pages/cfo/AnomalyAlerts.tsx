import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function AnomalyAlerts() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['cfo-anomalies'],
    queryFn: () => api.get('/v1/cfo/anomalies').then(r => r.data?.anomalies ?? r.data),
    refetchInterval: 60_000,
  })

  const ackMutation = useMutation({
    mutationFn: (id: string) => api.post(`/v1/cfo/anomalies/${id}/acknowledge`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cfo-anomalies'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Anomaly Alerts</h1>
          <p className="text-xs text-slate-400 mt-0.5">No employee identity shown — CFO sees financial pattern only</p>
        </div>
        {data?.length > 0 && <span className="badge badge-red">{data.length} active</span>}
      </div>

      {!isLoading && data?.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-12 text-center">
          <CheckCircle size={40} className="mx-auto text-emerald-400 mb-3" />
          <p className="text-slate-600 font-medium">No active anomalies</p>
        </div>
      )}

      <div className="space-y-3">
        {data?.map((a: any) => (
          <div key={a.anomaly_id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <div className="flex items-start gap-4">
              <AlertTriangle size={18} className={
                a.severity === 'HIGH' ? 'text-red-500' : 'text-amber-500'
              } />
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-slate-800">{a.type?.replace(/_/g,' ')}</span>
                  <span className={`badge ${a.severity === 'HIGH' ? 'badge-red' : 'badge-amber'}`}>
                    {a.severity}
                  </span>
                </div>
                <p className="text-sm text-slate-600 mt-1">{a.financial_pattern}</p>
                <p className="text-xs text-slate-400 font-mono mt-1">{fmtDateTime(a.detected_at)}</p>
                <p className="text-xs text-slate-400 mt-1">
                  Acknowledging will notify CHRO with employee identity context.
                </p>
              </div>
              <button onClick={() => ackMutation.mutate(a.anomaly_id)}
                      disabled={ackMutation.isPending}
                      className="flex items-center gap-1 text-xs font-medium text-indigo-600
                                 border border-indigo-200 px-3 py-1.5 rounded-lg hover:bg-indigo-50
                                 disabled:opacity-40 flex-shrink-0">
                <CheckCircle size={12}/> Acknowledge
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
