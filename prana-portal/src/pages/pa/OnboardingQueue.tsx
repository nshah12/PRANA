import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, CheckCircle, XCircle, Globe } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function OnboardingQueue() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['pa-onboarding'],
    queryFn: () => api.get('/admin/tenants?status_filter=PENDING').then(r => r.data),
  })

  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [overrideRegion, setOverrideRegion] = useState('')
  const [overrideReason, setOverrideReason] = useState('')

  const approveMutation = useMutation({
    mutationFn: ({ id, region, reason }: { id: string; region?: string; reason?: string }) =>
      api.post(`/admin/tenants/${id}/activate`, {
        home_region_override: region || undefined,
        override_reason: reason || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-onboarding'] })
      setApprovingId(null); setOverrideRegion(''); setOverrideReason('')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.post(`/admin/tenants/${id}/reject`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-onboarding'] }),
  })

  const tenants = data?.tenants ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Onboarding Queue</h1>
        <span className="badge badge-amber">{tenants.length} pending</span>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {!isLoading && tenants.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-12 text-center">
          <CheckCircle size={40} className="mx-auto text-emerald-400 mb-3" />
          <p className="text-slate-600 font-medium">No pending applications</p>
        </div>
      )}

      <div className="space-y-4">
        {tenants.map((t: any) => (
          <div key={t.tenant_id} className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
            <div className="px-6 py-5 flex items-start gap-4">
              <Building2 size={20} className="text-amber-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold text-slate-800">{t.tenant_name}</h3>
                  <span className="badge badge-muted">{t.industry}</span>
                  <span className="badge badge-amber">{t.tier}</span>
                </div>
                <div className="grid grid-cols-2 gap-x-8 gap-y-1 mt-3 text-xs text-slate-500">
                  <span>Domain: <span className="font-mono text-slate-700">{t.domain}</span></span>
                  <span>CIN: <span className="font-mono text-slate-700">{t.cin ?? '—'}</span></span>
                  <span>Size: <span className="font-mono text-slate-700">{t.employee_size_band}</span></span>
                  <span>Region: <span className="font-mono text-slate-700">{t.home_region ?? 'Auto'}</span></span>
                  <span>Applied: <span className="font-mono text-slate-700">{fmtDateTime(t.created_at)}</span></span>
                </div>
              </div>
            </div>

            {/* Region override (optional) */}
            {approvingId === t.tenant_id && (
              <div className="px-6 py-4 bg-amber-50 border-t border-amber-100 space-y-3">
                <p className="text-xs font-medium text-amber-700 flex items-center gap-1">
                  <Globe size={12}/> Override home region (optional — leave blank for auto)
                </p>
                <div className="flex gap-2">
                  <select value={overrideRegion} onChange={e => setOverrideRegion(e.target.value)}
                          className="border border-amber-200 rounded-lg px-3 py-2 text-sm bg-white
                                     focus:outline-none focus:ring-2 focus:ring-amber-400">
                    <option value="">Auto (recommended)</option>
                    <option value="ap-south-1">ap-south-1 (Mumbai)</option>
                    <option value="ap-south-2">ap-south-2 (Hyderabad)</option>
                  </select>
                  {overrideRegion && (
                    <input value={overrideReason} onChange={e => setOverrideReason(e.target.value)}
                           placeholder="Reason for override (required)"
                           className="flex-1 border border-amber-200 rounded-lg px-3 py-2 text-sm
                                      focus:outline-none focus:ring-2 focus:ring-amber-400" />
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => approveMutation.mutate({
                      id: t.tenant_id,
                      region: overrideRegion,
                      reason: overrideReason,
                    })}
                    disabled={approveMutation.isPending || (!!overrideRegion && !overrideReason)}
                    className="flex items-center gap-1 text-sm font-medium text-white bg-emerald-600
                               px-4 py-2 rounded-lg hover:bg-emerald-700 disabled:opacity-40">
                    <CheckCircle size={14}/> Confirm approval
                  </button>
                  <button onClick={() => setApprovingId(null)}
                          className="text-sm text-slate-500 hover:text-slate-700 px-3">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex gap-3">
              {approvingId !== t.tenant_id && (
                <button onClick={() => setApprovingId(t.tenant_id)}
                        className="flex items-center gap-1 text-sm font-medium text-emerald-600
                                   border border-emerald-200 px-4 py-1.5 rounded-lg hover:bg-emerald-50">
                  <CheckCircle size={13}/> Approve
                </button>
              )}
              <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                      className="flex items-center gap-1 text-sm font-medium text-red-500
                                 border border-red-200 px-4 py-1.5 rounded-lg hover:bg-red-50">
                <XCircle size={13}/> Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
