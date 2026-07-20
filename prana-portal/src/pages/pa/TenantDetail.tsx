import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, ShieldOff, ShieldCheck, ArrowLeft } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDate, fmtDateTime } from '@/lib/utils'

const LIFECYCLE_STATES = [
  { state: 'PENDING', access: 'No vault access yet', alumni: 'N/A', pa: 'Approve / Reject', reversible: '—' },
  { state: 'ACTIVE', access: 'Full vault access', alumni: 'Unaffected', pa: 'Suspend', reversible: '—' },
  { state: 'SUSPENDED', access: 'Login blocked, read-only', alumni: 'Unaffected', pa: 'Reinstate', reversible: 'Yes' },
  { state: 'OFFBOARDED', access: 'Data export + scheduled deletion', alumni: 'Permanently unaffected', pa: '—', reversible: 'No' },
]

export function TenantDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-tenant-detail', id],
    queryFn: () => api.get(`/admin/tenants/${id}`).then(r => r.data),
  })

  const suspendMutation = useMutation({
    mutationFn: (reason: string) => api.post(`/admin/tenants/${id}/suspend`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-tenant-detail', id] }),
  })

  const reinstateMutation = useMutation({
    mutationFn: () => api.post(`/admin/tenants/${id}/reinstate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-tenant-detail', id] }),
  })

  const handleSuspend = () => {
    const reason = window.prompt('Reason for suspending this tenant:')
    if (!reason) return
    if (!window.confirm(`Suspend ${t?.tenant_name}? This blocks all current employee/OA logins.`)) return
    suspendMutation.mutate(reason)
  }

  const handleReinstate = () => {
    if (!window.confirm(`Reinstate ${t?.tenant_name}? This restores full access.`)) return
    reinstateMutation.mutate()
  }

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="h-32 bg-slate-100 rounded-xl" />
      <div className="h-48 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load tenant.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-amber-600 hover:underline">Retry</button>
    </div>
  )

  const t = data?.tenant ?? data

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/admin/tenants')}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700">
        <ArrowLeft size={12}/> Back to Tenant Directory
      </button>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="flex items-start gap-3">
            <Building2 size={24} className="text-slate-400 mt-1" />
            <div>
              <h1 className="text-xl font-semibold text-slate-800">{t.tenant_name}</h1>
              <p className="text-sm font-mono text-slate-500">{t.domain}</p>
            </div>
          </div>
          <span className={`badge ${
            t.status === 'ACTIVE' ? 'badge-emerald' :
            t.status === 'SUSPENDED' ? 'badge-red' : 'badge-amber'
          }`}>{t.status}</span>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-3 mt-6 text-sm">
          <div><p className="text-xs text-slate-400">Industry</p><p className="text-slate-700">{t.industry ?? '—'}</p></div>
          <div><p className="text-xs text-slate-400">Employee headcount</p><p className="text-slate-700">{t.employee_headcount_band ?? '—'}</p></div>
          <div><p className="text-xs text-slate-400">SLA tier</p><p className="text-slate-700">{t.sla_tier ?? '—'}</p></div>
          <div><p className="text-xs text-slate-400">Home region</p><p className="text-slate-700">{t.home_region ?? '—'}</p></div>
          <div><p className="text-xs text-slate-400">CIN</p><p className="text-slate-700 font-mono">{t.cin ?? '—'}</p></div>
          <div><p className="text-xs text-slate-400">Domain verified</p><p className="text-slate-700">{t.domain_verified_at ? fmtDate(t.domain_verified_at) : 'Not yet'}</p></div>
          <div><p className="text-xs text-slate-400">Onboarded</p><p className="text-slate-700">{fmtDateTime(t.created_at)}</p></div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Lifecycle actions</h2>
        <div className="flex gap-3">
          {t.status === 'ACTIVE' && (
            <button onClick={handleSuspend} disabled={suspendMutation.isPending}
                    className="flex items-center gap-1.5 text-sm font-medium text-red-600
                               border border-red-200 px-4 py-2 rounded-lg hover:bg-red-50 disabled:opacity-40">
              <ShieldOff size={14}/> Suspend
            </button>
          )}
          {t.status === 'SUSPENDED' && (
            <button onClick={handleReinstate} disabled={reinstateMutation.isPending}
                    className="flex items-center gap-1.5 text-sm font-medium text-emerald-600
                               border border-emerald-200 px-4 py-2 rounded-lg hover:bg-emerald-50 disabled:opacity-40">
              <ShieldCheck size={14}/> Reinstate
            </button>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <h2 className="font-medium text-slate-800 px-6 pt-6 pb-3">Tenant lifecycle states</h2>
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-6 py-2 font-medium">State</th>
              <th className="text-left px-6 py-2 font-medium">Current employee access</th>
              <th className="text-left px-6 py-2 font-medium">Alumni access</th>
              <th className="text-left px-6 py-2 font-medium">PA action</th>
              <th className="text-left px-6 py-2 font-medium">Reversible</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {LIFECYCLE_STATES.map(row => (
              <tr key={row.state} className={row.state === t.status ? 'bg-amber-50' : undefined}>
                <td className="px-6 py-3"><span className="badge badge-muted">{row.state}</span></td>
                <td className="px-6 py-3 text-slate-600">{row.access}</td>
                <td className="px-6 py-3 text-slate-600">{row.alumni}</td>
                <td className="px-6 py-3 text-slate-600">{row.pa}</td>
                <td className="px-6 py-3 text-slate-600">{row.reversible}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
