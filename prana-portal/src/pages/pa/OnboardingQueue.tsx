import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, CheckCircle, XCircle, Globe, Clock, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import { tUi } from '@/i18n'

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
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_ONBOARD_TITLE')}</h1>
        <p className="text-xs text-slate-500 mt-1">{tUi('PA_ONBOARD_SUBTITLE')}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: tUi('PA_ONBOARD_STAT_PENDING_REVIEW'),   value: pendingReview.length,          sub: tUi('PA_ONBOARD_STAT_PENDING_REVIEW_SUB'),   color: 'amber' },
          { label: tUi('PA_ONBOARD_STAT_AUTO_APPROVED'),     value: autoApprovedToday.length,      sub: tUi('PA_ONBOARD_STAT_AUTO_APPROVED_SUB'),     color: 'emerald' },
          { label: tUi('PA_ONBOARD_STAT_AWAITING_VERIFY'),   value: awaitingVerification.length,   sub: tUi('PA_ONBOARD_STAT_AWAITING_VERIFY_SUB'),   color: 'sky' },
          { label: tUi('PA_ONBOARD_STAT_TOTAL_ACTIVE'),      value: activeData?.total ?? (activeData?.tenants?.length ?? '—'), sub: tUi('PA_ONBOARD_STAT_TOTAL_ACTIVE_SUB'), color: 'violet' },
        ].map(card => (
          <div key={card.label} className={`stat-card stat-card-${card.color}`}>
            <p className="text-2xl font-bold font-mono text-slate-800">{card.value}</p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
            <p className="text-[11px] text-slate-400 mt-0.5">{card.sub}</p>
          </div>
        ))}
      </div>

      <div className="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-xs text-sky-800">
        <span className="font-semibold">{tUi('PA_ONBOARD_TIER_BANNER_LABEL')}</span>{' '}
        <span className="badge badge-emerald mx-1">{TIER_LABEL.AUTO_APPROVE}</span>{tUi('PA_ONBOARD_TIER_STANDARD_DESC')}{' '}
        <span className="badge badge-amber mx-1">{TIER_LABEL.PA_REVIEW}</span>{tUi('PA_ONBOARD_TIER_BFSI_DESC')}{' '}
        <span className="badge badge-violet mx-1">{TIER_LABEL.PA_SALES_REVIEW}</span>{tUi('PA_ONBOARD_TIER_ENTERPRISE_DESC')}
      </div>

      {isLoading && <p className="text-sm text-slate-400">{tUi('CFO_DIGEST_LOADING')}</p>}

      {!isLoading && pendingReview.length === 0 && awaitingVerification.length === 0 && verificationFailed.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-12 text-center">
          <CheckCircle size={40} className="mx-auto text-emerald-400 mb-3" />
          <p className="text-slate-600 font-medium">{tUi('PA_ONBOARD_NONE')}</p>
        </div>
      )}

      {pendingReview.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">
            {tUi('PA_ONBOARD_STAT_PENDING_REVIEW')} <span className="badge badge-amber ml-1">{pendingReview.length} {tUi('PA_ONBOARD_APPLICATIONS_SUFFIX')}</span>
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
                    <span>{tUi('PA_ONBOARD_DOMAIN_LABEL')} <span className="font-mono text-slate-700">{t.domain}</span></span>
                    <span>{tUi('PA_ONBOARD_CIN_LABEL')} <span className="font-mono text-slate-700">{t.cin ?? '—'}</span></span>
                    <span>{tUi('PA_ONBOARD_SIZE_LABEL')} <span className="font-mono text-slate-700">{t.employee_headcount_band}</span></span>
                    <span>{tUi('PA_ONBOARD_REGION_LABEL')} <span className="font-mono text-slate-700">{t.home_region ?? tUi('PA_ONBOARD_AUTO_FALLBACK')}</span></span>
                    <span>{tUi('PA_ONBOARD_APPLIED_LABEL')} <span className="font-mono text-slate-700">{fmtDateTime(t.created_at)}</span></span>
                  </div>
                </div>
              </div>

              {approvingId === t.tenant_id && (
                <div className="px-6 py-4 bg-amber-50 border-t border-amber-100 space-y-3">
                  <p className="text-xs font-medium text-amber-700 flex items-center gap-1">
                    <Globe size={12}/> {tUi('PA_ONBOARD_OVERRIDE_REGION_NOTE')}
                  </p>
                  <div className="flex gap-2">
                    <select value={overrideRegion} onChange={e => setOverrideRegion(e.target.value)}
                            className="border border-amber-200 rounded-lg px-3 py-2 text-sm bg-white
                                       focus:outline-none focus:ring-2 focus:ring-amber-400">
                      <option value="">{tUi('PA_ONBOARD_AUTO_RECOMMENDED')}</option>
                      <option value="ap-south-1">{tUi('PA_ONBOARD_MUMBAI_OPTION')}</option>
                      <option value="ap-south-2">{tUi('PA_ONBOARD_HYDERABAD_OPTION')}</option>
                    </select>
                    {overrideRegion && (
                      <input value={overrideReason} onChange={e => setOverrideReason(e.target.value)}
                             placeholder={tUi('PA_ONBOARD_OVERRIDE_REASON_PLACEHOLDER')}
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
                      <CheckCircle size={14}/> {tUi('PA_ONBOARD_CONFIRM_APPROVAL')}
                    </button>
                    <button onClick={() => setApprovingId(null)}
                            className="text-sm text-slate-500 hover:text-slate-700 px-3">
                      {tUi('EMP_SHARES_CANCEL')}
                    </button>
                  </div>
                </div>
              )}

              <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex gap-3">
                {approvingId !== t.tenant_id && (
                  <button onClick={() => setApprovingId(t.tenant_id)}
                          className="flex items-center gap-1 text-sm font-medium text-emerald-600
                                     border border-emerald-200 px-4 py-1.5 rounded-lg hover:bg-emerald-50">
                    <CheckCircle size={13}/> {tUi('PA_ONBOARD_APPROVE')}
                  </button>
                )}
                <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                        className="flex items-center gap-1 text-sm font-medium text-red-500
                                   border border-red-200 px-4 py-1.5 rounded-lg hover:bg-red-50">
                  <XCircle size={13}/> {tUi('PA_ONBOARD_REJECT')}
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {(awaitingVerification.length > 0 || verificationFailed.length > 0) && (
        <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <h2 className="text-sm font-semibold text-slate-700 px-5 pt-5 pb-3">
            {tUi('PA_ONBOARD_SECTION_AWAITING_VERIFICATION')} <span className="badge badge-sky ml-1">{awaitingVerification.length + verificationFailed.length} {tUi('PA_ONBOARD_APPLICATIONS_SUFFIX')}</span>
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_ORGANISATION')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_DOMAIN')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_TIER')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_STATUS')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_ACTIONS')}</th>
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
                      ? tUi('PA_ONBOARD_REMAINING_HOURS', { hours: t.verification_remaining_hours })
                      : tUi('PA_ONBOARD_CHECKING')}
                  </td>
                  <td className="px-5 py-3">
                    <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                            className="text-xs text-red-500 hover:underline">{tUi('PA_ONBOARD_EXPIRE')}</button>
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
                    <span className="badge badge-red">{tUi('PA_ONBOARD_VERIFICATION_FAILED_BADGE')}</span>
                  </td>
                  <td className="px-5 py-3 flex items-center gap-3">
                    <button onClick={() => retryVerificationMutation.mutate(t.tenant_id)}
                            className="flex items-center gap-1 text-xs text-sky-600 hover:underline">
                      <RefreshCw size={11}/> {tUi('PA_ONBOARD_RETRY')}
                    </button>
                    <button onClick={() => rejectMutation.mutate(t.tenant_id)}
                            className="text-xs text-red-500 hover:underline">{tUi('PA_ONBOARD_REJECT')}</button>
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
            {tUi('PA_ONBOARD_SECTION_AUTO_APPROVED')} <span className="badge badge-emerald ml-1">{autoApprovedToday.length} {tUi('PA_ONBOARD_PROVISIONED_SUFFIX')}</span>
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_ORGANISATION')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_HOME_REGION')}</th>
                <th className="text-left px-5 py-2 font-medium">{tUi('PA_ONBOARD_COL_PROVISIONED')}</th>
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
