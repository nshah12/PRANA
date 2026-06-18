import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Plus, Building2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'

export function TenantDirectory() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['pa-tenants', search],
    queryFn: () => api.get('/admin/tenants', { params: { q: search || undefined } }).then(r => r.data),
  })

  const tenants = data?.tenants ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Tenant Directory</h1>
        <button
          onClick={() => navigate('/admin/tenants/new')}
          className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white text-sm
                     font-semibold rounded-lg hover:bg-amber-600 transition-colors">
          <Plus size={14}/> New Tenant
        </button>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={e => setSearch(e.target.value)}
               placeholder="Search by name or domain…"
               className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                          focus:outline-none focus:ring-2 focus:ring-amber-400" />
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Organisation</th>
              <th className="text-left px-5 py-3 font-medium">Domain</th>
              <th className="text-left px-5 py-3 font-medium">Industry</th>
              <th className="text-left px-5 py-3 font-medium">Size</th>
              <th className="text-left px-5 py-3 font-medium">State</th>
              <th className="text-left px-5 py-3 font-medium">SLA</th>
              <th className="text-left px-5 py-3 font-medium">Status</th>
              <th className="text-left px-5 py-3 font-medium">Since</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {!isLoading && tenants.length === 0 && (
              <tr>
                <td colSpan={8} className="px-5 py-12 text-center">
                  <Building2 size={32} className="mx-auto text-slate-300 mb-2" />
                  <p className="text-slate-500 text-sm font-medium">No tenants found</p>
                  <button onClick={() => navigate('/admin/tenants/new')}
                    className="mt-3 text-xs text-amber-600 font-medium hover:underline">
                    + Onboard your first tenant
                  </button>
                </td>
              </tr>
            )}
            {tenants.map((t: any) => (
              <tr key={t.tenant_id} className="hover:bg-canvas2 cursor-pointer"
                  onClick={() => navigate(`/admin/tenants/${t.tenant_id}`)}>
                <td className="px-5 py-3">
                  <div className="font-medium text-slate-800">{t.tenant_name}</div>
                  {t.cin && <div className="text-xs text-slate-400 font-mono">{t.cin}</div>}
                </td>
                <td className="px-5 py-3 font-mono text-xs text-slate-500">{t.domain}</td>
                <td className="px-5 py-3 text-xs text-slate-600">{t.industry ?? '—'}</td>
                <td className="px-5 py-3 text-xs text-slate-600">{t.employee_headcount_band ?? '—'}</td>
                <td className="px-5 py-3 text-slate-600">{t.primary_state ?? '—'}</td>
                <td className="px-5 py-3">
                  {t.sla_tier && (
                    <span className={`badge ${
                      t.sla_tier === 'ENTERPRISE' ? 'badge-violet' :
                      t.sla_tier === 'PRIORITY'   ? 'badge-amber' : 'badge-muted'
                    }`}>{t.sla_tier}</span>
                  )}
                </td>
                <td className="px-5 py-3">
                  <span className={`badge ${
                    t.status === 'ACTIVE'    ? 'badge-emerald' :
                    t.status === 'SUSPENDED' ? 'badge-red'     : 'badge-amber'
                  }`}>{t.status}</span>
                </td>
                <td className="px-5 py-3 text-xs text-slate-400">{fmtDate(t.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
