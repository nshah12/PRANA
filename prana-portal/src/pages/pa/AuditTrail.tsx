import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Download } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function AuditTrail() {
  const [search, setSearch] = useState('')
  const [eventType, setEventType] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['pa-audit', search, eventType, page],
    queryFn: () => api.get('/admin/audit', {
      params: { q: search||undefined, event_type: eventType||undefined, offset: page*100, limit: 100 }
    }).then(r => r.data),
  })

  async function exportAudit() {
    const res = await api.get('/admin/audit/export', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href=url; a.download='audit_export.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-slate-800">Audit Trail Explorer</h1>
        <button onClick={exportAudit}
                className="flex items-center gap-2 px-4 py-2 border border-slate-200
                           rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
          <Download size={14}/> Export CSV
        </button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)}
                 placeholder="Search by actor, tenant, resource…"
                 className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                            focus:outline-none focus:ring-2 focus:ring-amber-400" />
        </div>
        <input value={eventType} onChange={e => setEventType(e.target.value)}
               placeholder="Event type filter…"
               className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                          focus:outline-none focus:ring-2 focus:ring-amber-400 w-48" />
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Event</th>
              <th className="text-left px-5 py-3 font-medium">Actor</th>
              <th className="text-left px-5 py-3 font-medium">Tenant</th>
              <th className="text-left px-5 py-3 font-medium">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && <tr><td colSpan={4} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>}
            {data?.events?.map((e: any, i: number) => (
              <tr key={i} className="hover:bg-canvas2">
                <td className="px-5 py-3">
                  <span className="badge badge-muted font-mono text-xs">{e.event_type}</span>
                </td>
                <td className="px-5 py-3 text-xs text-slate-600 font-mono">{e.actor_id?.slice(0,8)}…</td>
                <td className="px-5 py-3 text-xs text-slate-600">{e.tenant_name ?? 'Platform'}</td>
                <td className="px-5 py-3 text-xs text-slate-400 font-mono">{fmtDateTime(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
