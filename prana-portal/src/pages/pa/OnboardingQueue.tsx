import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, CheckCircle, XCircle, Globe, Clock, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false
  return new Date(iso).toDateString() === new Date().toDateString()
}

const TIER_LABEL: Record<string, string> = {
  AUTO_APPROVE: 'Standard',
  PA_REVIEW: 'BFSI / Large',
  PA_SALES_REVIEW: 'Enterprise',
}

const TIER_BADGE: Record<string, string> = {
  AUTO_APPROVE: 'badge-emerald',
  PA_REVIEW: 'badge-amber',
  PA_SALES_REVIEW: 'badge-violet',
}

export function OnboardingQueue() {
  const qc = useQueryClient()

  const { data: pendingData, isLoading: pendingLoading } = useQuery({
    queryKey: ['pa-onboarding-pending'],
    queryFn: () => api.get('/admin/tenants?status=PENDING').then(r => r.data),
  })
  const { data: activeData } = useQuery({
    queryKey: ['pa-onboarding-active'],
    queryFn: () => api.get('/admin/tenants?status=ACTIVE').then(r => r.data),
  })
  const { data: failedData } = useQuery({
    queryKey: ['pa-onboarding-failed'],
    queryFn: () => api.get('/admin/tenants?status=VERIFICATION_FAILED').then(r => r.data),
  })

  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [overrideRegion, setOverrideRegion] = useState('')
  const [overrideReason, setOverrideReason] = useState('')

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['pa-onboarding-pending'] })
    qc.invalidateQueries({ queryKey: ['pa-onboarding-active'] })
    qc.invalidateQueries({ queryKey: ['pa-onboarding-failed'] })
  }

  const approveMutation = useMutation({
    mutationFn: ({ id, region, reason }: { id: string; region?: string; reason?: string }) =>
      api.post(`/admin/tenants/${id}/activate`, {
        home_region_override: region || undefined,
        override_reason: reason || undefined,
      }),
    onSuccess: () => {
      invalidateAll()
      setApprovingId(null); setOverrideRegion(''); setOverrideReason('')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.post(`/admin/tenants/${id}/reject`),
    onSuccess: invalidateAll,
  })

  const retryVerificationMutation = useMutation({
    mutationFn: (id: string) => api.post(`/admin/tenants/${id}/retry-verification`),
    onSuccess: invalidateAll,
  })

  const pending = pendingData?.tenants ?? []
  const awaitingVerification = pending.filter((t: any) => !t.domain_verified_at)
  const pendingReview = pending.filter((t: any) => t.domain_verified_at)
  const autoApprovedToday = (activeData?.tenants ?? [])
    .filter((t: any) => t.approval_tier === 'AUTO_APPROVE' && isToday(t.created_at))
  const verificationFailed = failedData?.tenants ?? []

  const isLoading = pendingLoading

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Organisation Onboarding Queue</h1>
        <p className="text-xs text-slate-500 mt-1">
          Review self-registered and PA-assisted applications. Auto-approval handles standard cases.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Pending PA Review', value: pendingReview.length, sub: 'BFSI + large enterprise', color: 'amber' },
          { label: 'Auto-Approved Today', value: autoApprovedToday.length, sub: 'Standard tier', color: 'emerald' },
          { label: 'Awaiting Domain Verify', value: awaitingVerification.length, sub: 'Self-registered, pending', color: 'sky' },
          { label: 'Total Active Tenants', value: activeData?.total ?? (activeData?.tenants?.length ?? '—'), sub: 'All tiers', color: 'violet' },
        ].map(card => (
          <div key={card.label} className={`stat-card stat-card-${card.color}`}>
            <p className="text-2xl font-bold font-mono text-slate-800">{card.value}</p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
            <p className="text-[11px] text-slate-400 mt-0.5">{card.sub}</p>
          </div>
        ))}
      </div>

      <div className="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-xs text-sky-800">
        <span className="font-semibold">Tiered Auto-Approval:</span>{' '}
        <span className="badge badge-emerald mx-1">Standard</span>1-500 employees, non-BFSI, domain verified → auto-approved.{' '}
        <span className="badge badge-amber mx-1">BFSI / Large</span>BFSI or 501-2,000 employees → PA manual review.{' '}
        <span className="badge badge-violet mx-1">Enterprise</span>2,001+ employees → PA + Sales review.
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      {!isLoading && pendingReview.length === 0 && awaitingVerification.length === 0 && verificationFailed.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-12 text-center">
          <CheckCircle size={40} className="mx-auto text-emerald-400 mb-3" />
          <p className="text-slate-600 font-medium">No pending applications</p>
        </div>
      )}

      {pendingReview.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">
            Pending PA Review <span className="badge badge-amber ml-1">{pendingReview.length} applications</span>
          </h2>
          {pendingReview.map((t: any) => (
            <div key={t.tenant_id} className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
              <div className="px-6 py-5 flex items-start gap-4">
                <Building2 size={20} className="text-amber-500 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-slate-800">{t.tenant_name}</h3>
                    <span className="badge badge-muted">{t.industry}</span>
                    <span className={`badge ${TIER_BADGE[t.approval_tier] ?? 'badge-muted'}`}>
                      {TIER_LABEL[t.approval_tier] ?? t.approval_tier}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-1 mt-3 text-xs text-slate-500">
                    <span>Domain: <span className="font-mono text-slate-700">{t.domain}</span></span>
                    <span>CIN: <span className="font-mono text-slate-700">{t.cin ?? '—'}</span></span>
                    <span>Size: <span className="font-mono text-slate-700">{t.employee_headcount_band}</span></span>
                    <span>Region: <span className="font-mono text-slate-700">{t.home_region ?? 'Auto'}</span></span>
                    <span>Applied: <span className="font-mono text-slate-700">{fmtDateTime(t.created_at)}</span></span>
                  </div>
                </div>
              </div>

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
        </section>
      )}

      {(awaitingVerification.length > 0 || verificationFailed.length > 0) && (
        <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <h2 className="text-sm font-semibold text-slate-700 px-5 pt-5 pb-3">
            Awaiting Domain Verification <span className="badge badge-sky ml-1">{awaitingVerification.length + verificationFailed.length} applications</span>
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-2 font-medium">Organisation</th>
                <th className="text-left px-5 py-2 font-medium">Domain</th>
                <th className="text-left px-5 py-2 font-medium">Tier</th>
                <th className="text-left px-5 py-2 font-medium">Status</th>
                <th className="text-left px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {awaitingVerification.map((t: any) => (
                <tr key={t.tenant_id}>
                  <td className="px-5 py-3 font-medium text-slate-800">{t.tenant_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">{t.domain}</td>
                  <td className="px-5 py-3">
                    <span className={`badge ${TIER_BADGE[t.approval_tier] ?? 'badge-muted'}`}>
                      {TIER_LABEL[t.approval_tier] ?? t.approval_tier}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500 flex items-center gap-1">
                    <Clock size={12}/>
                    {t.verification_remaining_hours != null
                      ? `${t.verification_remaining_hours}h remaining`
                      : 'checking…'}
                  </td>
                  <td className="px-5 py-3">
                    <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                            className="text-xs text-red-500 hover:underline">Expire</button>
                  </td>
                </tr>
              ))}
              {verificationFailed.map((t: any) => (
                <tr key={t.tenant_id}>
                  <td className="px-5 py-3 font-medium text-slate-800">{t.tenant_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">{t.domain}</td>
                  <td className="px-5 py-3">
                    <span className={`badge ${TIER_BADGE[t.approval_tier] ?? 'badge-muted'}`}>
                      {TIER_LABEL[t.approval_tier] ?? t.approval_tier}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className="badge badge-red">Verification failed</span>
                  </td>
                  <td className="px-5 py-3 flex items-center gap-3">
                    <button onClick={() => retryVerificationMutation.mutate(t.tenant_id)}
                            className="flex items-center gap-1 text-xs text-sky-600 hover:underline">
                      <RefreshCw size={11}/> Retry
                    </button>
                    <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                            className="text-xs text-red-500 hover:underline">Reject</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {autoApprovedToday.length > 0 && (
        <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <h2 className="text-sm font-semibold text-slate-700 px-5 pt-5 pb-3">
            Auto-Approved Today <span className="badge badge-emerald ml-1">{autoApprovedToday.length} provisioned</span>
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-2 font-medium">Organisation</th>
                <th className="text-left px-5 py-2 font-medium">Home region</th>
                <th className="text-left px-5 py-2 font-medium">Provisioned</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {autoApprovedToday.map((t: any) => (
                <tr key={t.tenant_id}>
                  <td className="px-5 py-3 font-medium text-slate-800">{t.tenant_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">{t.home_region}</td>
                  <td className="px-5 py-3 text-xs text-slate-400">{fmtDateTime(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
