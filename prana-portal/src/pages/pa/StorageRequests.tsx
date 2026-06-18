import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Clock } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function StorageRequests() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['pa-storage'],
    queryFn: () => api.get('/admin/storage-requests').then(r => r.data),
  })
  const decideMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'approve'|'reject'|'hold' }) =>
      api.post(`/admin/storage-requests/${id}/${decision}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-storage'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Storage Requests</h1>
        <span className="badge badge-amber">{data?.filter((r: any) => r.status==='PENDING').length ?? 0} pending</span>
      </div>
      <div className="space-y-3">
        {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {data?.map((req: any) => (
          <div key={req.request_id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <p className="font-medium text-slate-800">{req.tenant_name}</p>
                <p className="text-sm text-slate-500 mt-0.5">
                  Requesting <span className="font-mono font-bold">{req.requested_gb} GB</span> · Current: {req.current_gb} GB
                </p>
                <p className="text-xs text-slate-400 mt-1">{fmtDateTime(req.requested_at)}</p>
                {req.reason && <p className="text-sm text-slate-600 mt-2 bg-slate-50 rounded-md px-3 py-2">{req.reason}</p>}
              </div>
              {req.status === 'PENDING' && (
                <div className="flex gap-2 flex-shrink-0">
                  {(['approve','hold','reject'] as const).map(d => (
                    <button key={d} onClick={() => decideMutation.mutate({ id: req.request_id, decision: d })}
                            className={`flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                              d==='approve' ? 'text-emerald-600 border-emerald-200 hover:bg-emerald-50' :
                              d==='reject'  ? 'text-red-500 border-red-200 hover:bg-red-50' :
                                             'text-amber-600 border-amber-200 hover:bg-amber-50'
                            }`}>
                      {d==='approve'?<CheckCircle size={11}/>:d==='reject'?<XCircle size={11}/>:<Clock size={11}/>}
                      {d.charAt(0).toUpperCase()+d.slice(1)}
                    </button>
                  ))}
                </div>
              )}
              {req.status !== 'PENDING' && (
                <span className={`badge ${req.status==='APPROVED'?'badge-emerald':req.status==='REJECTED'?'badge-red':'badge-amber'}`}>
                  {req.status}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
