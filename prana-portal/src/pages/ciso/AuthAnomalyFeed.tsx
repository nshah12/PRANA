import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LogOut, AlertTriangle, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function AuthAnomalyFeed() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['ciso-auth-anomalies'],
    queryFn: () => api.get('/v1/ciso/auth-anomalies').then(r => r.data),
    refetchInterval: 20_000,
  })

  const forceLogoutMutation = useMutation({
    mutationFn: (sessionId: string) => api.post(`/auth/sessions/${sessionId}/revoke`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-auth-anomalies'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Auth Anomaly Feed</h1>
        <button onClick={() => qc.invalidateQueries({ queryKey: ['ciso-auth-anomalies'] })}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800">
          <RefreshCw size={12}/> Refresh
        </button>
      </div>

      <div className="space-y-3">
        {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {data?.anomalies?.length === 0 && (
          <div className="bg-white rounded-xl border border-slate-100 p-12 text-center">
            <p className="text-slate-500">No auth anomalies detected.</p>
          </div>
        )}
        {data?.anomalies?.map((a: any) => (
          <div key={a.event_id}
               className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 flex items-start gap-4">
            <AlertTriangle size={18} className="text-red-500 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-slate-800">{a.anomaly_type?.replace(/_/g,' ')}</span>
                <span className={`badge ${a.severity === 'HIGH' ? 'badge-red' : 'badge-amber'}`}>
                  {a.severity}
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-1">{a.description}</p>
              <div className="flex items-center gap-4 mt-2 text-xs text-slate-400 font-mono">
                <span>IP: {a.ip_address}</span>
                <span>{fmtDateTime(a.detected_at)}</span>
              </div>
            </div>
            {a.session_id && (
              <button
                onClick={() => {
                  if (confirm('Force logout this session?')) {
                    forceLogoutMutation.mutate(a.session_id)
                  }
                }}
                className="flex items-center gap-1 text-xs font-medium text-red-600
                           border border-red-200 px-3 py-1.5 rounded-lg hover:bg-red-50 flex-shrink-0">
                <LogOut size={12}/> Force logout
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
