import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

export function EmpVaultHealth() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['emp-vault-health'],
    queryFn: () => api.get('/v1/vault/health').then(r => r.data),
  })
  const { data: profileData } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/v1/vault/profile').then(r => r.data),
  })
  const { data: docsData } = useQuery({
    queryKey: ['emp-vault-docs'],
    queryFn: () => api.get('/v1/vault/documents', { params: { limit: 100 } }).then(r => r.data),
  })

  const score      = data?.overall_score ?? 0
  const gapCount   = data?.gap_count     ?? 0
  const gaps: any[]= data?.gap_detail    ?? []
  const employers: any[] = profileData?.employers ?? []
  const docs: any[]      = docsData?.documents ?? []

  const scoreColor =
    score >= 80 ? '#10B981' :
    score >= 50 ? '#F59E0B' : '#EF4444'

  // Build breakdown rows from actual data
  const hasEmploymentProof = docs.some(d => ['APPOINTMENT_LETTER','OFFER_LETTER'].includes(d.doc_type))
  const recentSlips = docs.filter(d => {
    if (d.doc_type !== 'SALARY_SLIP') return false
    const period = d.doc_period
    if (!period) return false
    const [y,m] = period.split('-').map(Number)
    const docDate = new Date(y, (m||1)-1)
    const cutoff  = new Date()
    cutoff.setMonth(cutoff.getMonth() - 12)
    return docDate >= cutoff
  })
  const form16Docs  = docs.filter(d => d.doc_type === 'FORM_16')
  const alumniOrgs  = employers.filter((e:any) => e.dol)
  const missingHistoric = alumniOrgs.some(
    (e:any) => !docs.some(d => d.tenant_id === (e.tenant_id ?? e.id) && d.doc_type === 'SALARY_SLIP')
  )

  const breakdown = [
    { label: tUi('EMP_VAULT_HEALTH_EMPLOYMENT_PROOF'),         st: hasEmploymentProof ? 'ok' : 'bad' },
    { label: tUi('EMP_VAULT_HEALTH_SALARY_SLIPS_12MO'), st: recentSlips.length >= 6 ? 'ok' : recentSlips.length > 0 ? 'warn' : 'bad' },
    { label: tUi('EMP_VAULT_HEALTH_FORM16_HISTORY'),          st: form16Docs.length >= employers.length ? 'ok' : form16Docs.length > 0 ? 'warn' : 'bad' },
    { label: tUi('EMP_VAULT_HEALTH_HISTORIC_SLIPS'),  st: missingHistoric ? 'bad' : 'ok' },
  ]

  const computedScore = score > 0 ? score :
    Math.round(breakdown.filter(r => r.st === 'ok').length / breakdown.length * 100)

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-slate-800 mb-1">{tUi('EMP_LAYOUT_NAV_VAULT_HEALTH')}</h1>
      <p className="text-sm text-slate-500 mb-5">{tUi('EMP_VAULT_HEALTH_SUB')}</p>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_,i) => <div key={i} className="h-24 bg-slate-100 animate-pulse rounded-xl"/>)}
        </div>
      ) : (
        <>
          {/* Score + breakdown */}
          <div className="grid gap-4 mb-5" style={{ gridTemplateColumns: '190px 1fr' }}>
            <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col items-center text-center shadow-sm">
              <p className="font-bold leading-none" style={{ fontSize: 52, color: scoreColor }}>
                {computedScore}%
              </p>
              <p className="text-xs font-semibold text-slate-600 mt-2">{tUi('EMP_VAULT_HEALTH_SCORE_LABEL')}</p>
              <div className="w-full h-1.5 bg-slate-100 rounded-full mt-3 overflow-hidden">
                <div className="h-full rounded-full transition-all"
                  style={{ width: `${computedScore}%`, background: 'linear-gradient(90deg,#10B981,#0EA5E9)' }}/>
              </div>
              {gapCount > 0 && (
                <p className="text-[11px] mt-2 font-semibold" style={{ color: '#F59E0B' }}>
                  {gapCount} gap{gapCount !== 1 ? 's' : ''} found
                </p>
              )}
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-3">{tUi('EMP_VAULT_HEALTH_SCORE_BREAKDOWN')}</p>
              <div className="space-y-2.5">
                {breakdown.map(row => (
                  <div key={row.label} className="flex items-center justify-between gap-3">
                    <span className="text-sm text-slate-700">{row.label}</span>
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded border shrink-0"
                      style={row.st === 'ok'
                        ? { background:'rgba(16,185,129,0.08)', color:'#059669', borderColor:'rgba(16,185,129,0.25)' }
                        : row.st === 'warn'
                        ? { background:'rgba(245,158,11,0.08)', color:'#D97706', borderColor:'rgba(245,158,11,0.25)' }
                        : { background:'rgba(239,68,68,0.06)', color:'#DC2626', borderColor:'rgba(239,68,68,0.2)' }
                      }>
                      {row.st === 'ok' ? tUi('EMP_VAULT_HEALTH_COMPLETE') : row.st === 'warn' ? tUi('EMP_VAULT_HEALTH_PARTIAL') : tUi('EMP_VAULT_HEALTH_MISSING')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Gaps */}
          {(gapCount > 0 || gaps.length > 0 || missingHistoric || breakdown.some(r => r.st !== 'ok')) ? (
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-3">{tUi('EMP_VAULT_HEALTH_GAPS_FOUND_TITLE')}</p>
              <div className="space-y-3">
                {/* From API */}
                {gaps.map((g: any, i: number) => (
                  <div key={i} className="p-3 rounded-lg"
                    style={{ background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.2)' }}>
                    <p className="text-sm font-semibold text-slate-800">📋 {g.description ?? g.gap_type}</p>
                    {g.employer && <p className="text-xs text-slate-500 mt-0.5">{tUi('EMP_VAULT_HEALTH_EMPLOYER_PREFIX')} {g.employer}</p>}
                    <button onClick={() => navigate('/emp/doc-request')} className="mt-1.5 text-xs font-semibold text-sky-600 hover:underline">{tUi('EMP_VAULT_HEALTH_REQUEST_BTN')}</button>
                  </div>
                ))}

                {/* Synthesized from local data */}
                {form16Docs.length < employers.length && (
                  <div className="p-3 rounded-lg"
                    style={{ background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.2)' }}>
                    <p className="text-sm font-semibold text-slate-800">{tUi('EMP_VAULT_HEALTH_FORM16_MISSING_TITLE')}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{tUi('EMP_VAULT_HEALTH_FORM16_MISSING_SUB')}</p>
                    <button onClick={() => navigate('/emp/doc-request')} className="mt-1.5 text-xs font-semibold text-sky-600 hover:underline">{tUi('EMP_VAULT_HEALTH_REQUEST_BTN')}</button>
                  </div>
                )}
                {missingHistoric && (
                  <div className="p-3 rounded-lg"
                    style={{ background:'rgba(239,68,68,0.04)', border:'1px solid rgba(239,68,68,0.15)' }}>
                    <p className="text-sm font-semibold text-slate-800">{tUi('EMP_VAULT_HEALTH_HISTORIC_MISSING_TITLE')}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{tUi('EMP_VAULT_HEALTH_HISTORIC_MISSING_SUB')}</p>
                    {/* TODO(product): no portal self-upload page exists yet (self-upload is
                        mobile-only, see prana-mobile/src/app/(vault)/vault/self-upload.tsx) —
                        disabled with an honest tooltip rather than linking somewhere wrong. */}
                    <button disabled title={tUi('EMP_VAULT_HEALTH_SELF_UPLOAD_MOBILE_ONLY')} className="mt-1.5 text-xs font-semibold text-slate-400 cursor-not-allowed">{tUi('EMP_VAULT_HEALTH_SELF_UPLOAD_BTN')}</button>
                  </div>
                )}
              </div>
            </div>
          ) : computedScore > 0 ? (
            <div className="rounded-xl p-5 text-center border"
              style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
              <p className="text-3xl mb-2">✅</p>
              <p className="font-bold text-emerald-700">{tUi('EMP_VAULT_HEALTH_COMPLETE_TITLE')}</p>
              <p className="text-sm text-emerald-600 mt-1">{tUi('EMP_VAULT_HEALTH_COMPLETE_SUB')}</p>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
